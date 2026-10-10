package com.ivpds.history;

import com.ivpds.analysis.Analysis;
import com.ivpds.analysis.RiskResult;
import com.ivpds.call.CallSource;
import com.ivpds.common.PageResponse;
import java.math.BigDecimal;
import java.sql.Array;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

/**
 * Truy vấn đọc cho lịch sử: mỗi dòng là một cuộc gọi kèm lần phân tích mới nhất của nó.
 *
 * <p>Viết bằng SQL thay vì JPA vì một dòng gộp sáu bảng (cuộc gọi, audio, lần phân tích mới nhất, kết quả, dấu
 * hiệu, người dùng) và cần lọc, phân trang ngay trong database. Lớp này chỉ đọc; mọi thao tác ghi vẫn qua JPA.
 * Dùng chung cho lịch sử của người dùng (lọc theo chủ cuộc gọi) và trang quản trị (không lọc theo chủ).
 */
@Repository
public class CallHistoryQueries {

    private static final String FROM = """
              from call_records c
              join users u on u.id = c.user_id
              left join audio_files f on f.call_record_id = c.id
              left join lateral (select x.* from analyses x where x.call_record_id = c.id
                                  order by x.created_at desc limit 1) a on true
              left join risk_results r on r.analysis_id = a.id
              left join transcripts t on t.analysis_id = a.id
            """;
    private static final String COLUMNS = """
            select c.id as call_id, c.caller_number, c.called_at, c.source, c.created_at,
                   u.id as user_id, u.email as user_email, u.full_name as user_full_name,
                   f.duration_seconds,
                   a.id as analysis_id, a.status, a.error_code, a.error_message, a.completed_at,
                   r.risk_score, r.risk_level, r.confidence, r.model_probability,
                   r.nlp_model_version, r.ruleset_version, r.risk_engine_version,
                   t.content as transcript, t.stt_model,
                   (select coalesce(array_agg(i.indicator_code order by i.indicator_code), '{}')
                      from risk_indicators i where i.risk_result_id = r.id) as indicators,
                   exists(select 1 from blacklist_numbers b
                           where b.phone_number = c.caller_number and b.active) as caller_blacklisted
            """;

    private final NamedParameterJdbcTemplate jdbc;

    public CallHistoryQueries(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /**
     * Điều kiện lọc; trường nào null thì không lọc theo trường đó.
     *
     * @param userId       chỉ cuộc gọi của người dùng này (bắt buộc với API của người dùng, tùy chọn với quản trị)
     * @param riskLevel    mức rủi ro của lần phân tích mới nhất
     * @param status       trạng thái của lần phân tích mới nhất
     * @param from         cuộc gọi được gửi lên từ thời điểm này
     * @param to           cuộc gọi được gửi lên trước thời điểm này
     * @param callerDigits chuỗi chữ số có trong số người gọi
     */
    public record Filter(UUID userId, RiskResult.Level riskLevel, Analysis.Status status, Instant from, Instant to,
            String callerDigits) {
    }

    /** Một trang cuộc gọi khớp điều kiện lọc, mới nhất trước. */
    public PageResponse<Row> search(Filter filter, int page, int size) {
        MapSqlParameterSource params = new MapSqlParameterSource();
        String where = where(filter, params);
        long total = jdbc.queryForObject("select count(*) " + FROM + where, params, Long.class);
        params.addValue("limit", size).addValue("offset", (long) page * size);
        List<Row> rows = jdbc.query(COLUMNS + FROM + where + " order by c.created_at desc limit :limit offset :offset",
                params, (rs, index) -> row(rs, false));
        return new PageResponse<>(rows, page, size, total, (int) Math.ceil((double) total / size));
    }

    /** Một cuộc gọi kèm transcript đầy đủ; {@code userId} null nghĩa là không kiểm tra chủ cuộc gọi (quản trị). */
    public Optional<Row> find(UUID callId, UUID userId) {
        MapSqlParameterSource params = new MapSqlParameterSource("callId", callId);
        String where = " where c.id = :callId";
        if (userId != null) {
            where += " and c.user_id = :userId";
            params.addValue("userId", userId);
        }
        return jdbc.query(COLUMNS + FROM + where, params, (rs, index) -> row(rs, true)).stream().findFirst();
    }

    private static String where(Filter filter, MapSqlParameterSource params) {
        List<String> conditions = new ArrayList<>();
        if (filter.userId() != null) {
            conditions.add("c.user_id = :userId");
            params.addValue("userId", filter.userId());
        }
        if (filter.riskLevel() != null) {
            conditions.add("r.risk_level = :riskLevel");
            params.addValue("riskLevel", filter.riskLevel().name());
        }
        if (filter.status() != null) {
            conditions.add("a.status = :status");
            params.addValue("status", filter.status().name());
        }
        if (filter.from() != null) {
            conditions.add("c.created_at >= :from");
            params.addValue("from", Timestamp.from(filter.from()));
        }
        if (filter.to() != null) {
            conditions.add("c.created_at < :to");
            params.addValue("to", Timestamp.from(filter.to()));
        }
        if (filter.callerDigits() != null && !filter.callerDigits().isEmpty()) {
            conditions.add("c.caller_number like :caller");
            params.addValue("caller", "%" + filter.callerDigits() + "%");
        }
        return conditions.isEmpty() ? "" : " where " + String.join(" and ", conditions);
    }

    /** Một cuộc gọi kèm lần phân tích mới nhất; {@code analysisId} null nghĩa là cuộc gọi chưa được phân tích. */
    public record Row(
            UUID callId, String callerNumber, boolean callerBlacklisted, Instant calledAt, CallSource source,
            Instant createdAt, BigDecimal durationSeconds,
            UUID userId, String userEmail, String userFullName,
            UUID analysisId, Analysis.Status status, String errorCode, String errorMessage, Instant completedAt,
            Integer riskScore, RiskResult.Level riskLevel, BigDecimal confidence, List<String> indicators,
            String transcript, String sttModel, BigDecimal modelProbability, String nlpModelVersion,
            String rulesetVersion, String riskEngineVersion) {
    }

    /** Đọc một dòng kết quả; transcript chỉ được lấy khi xem chi tiết để danh sách không phải tải văn bản dài. */
    private static Row row(ResultSet rs, boolean withTranscript) throws SQLException {
        String status = rs.getString("status");
        String riskLevel = rs.getString("risk_level");
        Array indicators = rs.getArray("indicators");
        return new Row(
                rs.getObject("call_id", UUID.class), rs.getString("caller_number"),
                rs.getBoolean("caller_blacklisted"), instant(rs, "called_at"),
                CallSource.valueOf(rs.getString("source")), instant(rs, "created_at"),
                rs.getBigDecimal("duration_seconds"),
                rs.getObject("user_id", UUID.class), rs.getString("user_email"), rs.getString("user_full_name"),
                rs.getObject("analysis_id", UUID.class),
                status == null ? null : Analysis.Status.valueOf(status), rs.getString("error_code"),
                rs.getString("error_message"), instant(rs, "completed_at"),
                (Integer) rs.getObject("risk_score", Integer.class),
                riskLevel == null ? null : RiskResult.Level.valueOf(riskLevel), rs.getBigDecimal("confidence"),
                riskLevel == null ? null : Arrays.asList((String[]) indicators.getArray()),
                withTranscript ? rs.getString("transcript") : null, rs.getString("stt_model"),
                rs.getBigDecimal("model_probability"), rs.getString("nlp_model_version"),
                rs.getString("ruleset_version"), rs.getString("risk_engine_version"));
    }

    private static Instant instant(ResultSet rs, String column) throws SQLException {
        Timestamp value = rs.getTimestamp(column);
        return value == null ? null : value.toInstant();
    }
}
