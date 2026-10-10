package com.ivpds.admin;

import com.ivpds.common.error.ApiException;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.sql.Timestamp;
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.temporal.ChronoUnit;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * API thống kê cho dashboard và báo cáo của trang quản trị, chỉ dành cho ADMIN.
 *
 * <p>Mọi con số được đếm trực tiếp từ database tại thời điểm gọi; không có số nào được lưu sẵn hay ước lượng.
 * Mức rủi ro của một cuộc gọi là mức của lần phân tích hoàn tất mới nhất của nó.
 */
@RestController
@RequestMapping("/api/v1/admin/statistics")
@Tag(name = "Admin: statistics")
public class AdminStatisticsController {

    private static final int MAX_DAYS = 365;
    private static final int TOP_INDICATORS = 10;
    private static final int SUSPECTED_NUMBERS = 10;

    private final JdbcTemplate jdbc;
    private final ZoneId defaultZone;

    public AdminStatisticsController(JdbcTemplate jdbc,
            @Value("${ivpds.reports.time-zone}") ZoneId defaultZone) {
        this.jdbc = jdbc;
        this.defaultZone = defaultZone;
    }

    /**
     * Số liệu tổng quan của hệ thống.
     *
     * @param periodDays      số ngày của giai đoạn được thống kê theo ngày
     * @param timeZone        múi giờ dùng để chia ngày trong báo cáo
     * @param users           số tài khoản: tổng, đang hoạt động, bị khóa, mới trong giai đoạn
     * @param calls           số cuộc gọi: tổng, theo nguồn, mới trong giai đoạn
     * @param analysesByStatus số lần phân tích theo trạng thái
     * @param callsByRiskLevel số cuộc gọi theo mức rủi ro của lần phân tích hoàn tất mới nhất
     * @param topIndicators   các dấu hiệu lừa đảo xuất hiện nhiều nhất
     * @param blacklist       số dòng của danh sách đen: tổng và đang chặn
     * @param blacklistReports số báo cáo số lừa đảo của người dùng theo trạng thái
     * @param phishingPatterns số mẫu lừa đảo: tổng và đang bật
     * @param suspectedNumbers các số gọi đến có cuộc gọi mức HIGH mà chưa nằm trong danh sách đen
     * @param daily           số cuộc gọi mỗi ngày trong giai đoạn, chia theo mức rủi ro
     */
    public record Statistics(
            Instant generatedAt,
            int periodDays,
            String timeZone,
            Map<String, Long> users,
            Map<String, Long> calls,
            Map<String, Long> analysesByStatus,
            Map<String, Long> callsByRiskLevel,
            List<IndicatorCount> topIndicators,
            Map<String, Long> blacklist,
            Map<String, Long> blacklistReports,
            Map<String, Long> phishingPatterns,
            List<SuspectedNumber> suspectedNumbers,
            List<DailyCount> daily) {
    }

    /**
     * Một số gọi đến đáng xem xét đưa vào danh sách đen: đã có cuộc gọi bị đánh giá mức HIGH và hiện chưa bị chặn.
     * Đây là gợi ý để quản trị viên xem lại, không phải kết luận: model vẫn có thể báo nhầm.
     *
     * @param highRiskCalls số cuộc gọi mức HIGH từ số này
     * @param users         số người dùng khác nhau đã nhận các cuộc gọi đó
     */
    public record SuspectedNumber(String phoneNumber, long highRiskCalls, long users, Instant lastCallAt) {
    }

    /** Số cuộc gọi có một dấu hiệu. */
    public record IndicatorCount(String indicator, long calls) {
    }

    /**
     * Số cuộc gọi được gửi lên trong một ngày.
     *
     * @param unanalysed cuộc gọi chưa có lần phân tích hoàn tất nào
     */
    public record DailyCount(LocalDate date, long calls, long high, long medium, long low, long unanalysed) {
    }

    /**
     * Dashboard và báo cáo.
     *
     * @param days     độ dài giai đoạn thống kê theo ngày, mặc định 30
     * @param timeZone múi giờ để chia ngày (ví dụ Asia/Ho_Chi_Minh); bỏ trống thì dùng múi giờ cấu hình sẵn. Một
     *                 cuộc gọi lúc 6 giờ sáng ở Việt Nam thuộc ngày hôm đó, không phải ngày hôm trước theo giờ UTC
     */
    @GetMapping
    @Operation(summary = "Admin: dashboard numbers and per-day report for the last N days")
    public Statistics statistics(@RequestParam(defaultValue = "30") int days,
            @RequestParam(required = false) String timeZone) {
        ZoneId zone = defaultZone;
        if (timeZone != null && !timeZone.isBlank()) {
            try {
                zone = ZoneId.of(timeZone.trim());
            } catch (DateTimeException e) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_TIME_ZONE",
                        "timeZone must be a zone id such as Asia/Ho_Chi_Minh.");
            }
        }
        int period = Math.min(Math.max(days, 1), MAX_DAYS);
        LocalDate today = LocalDate.now(zone);
        LocalDate firstDay = today.minusDays(period - 1L);
        Timestamp since = Timestamp.from(firstDay.atStartOfDay(zone).toInstant());

        Map<String, Long> users = new LinkedHashMap<>();
        users.put("total", count("select count(*) from users"));
        users.put("active", count("select count(*) from users where status = 'ACTIVE'"));
        users.put("locked", count("select count(*) from users where status = 'LOCKED'"));
        users.put("newInPeriod", count("select count(*) from users where created_at >= ?", since));

        Map<String, Long> calls = new LinkedHashMap<>();
        calls.put("total", count("select count(*) from call_records"));
        calls.put("newInPeriod", count("select count(*) from call_records where created_at >= ?", since));
        calls.putAll(grouped("select source, count(*) from call_records group by source", "RECORDED", "UPLOADED",
                "LIVE"));

        Map<String, Long> analyses = grouped("select status, count(*) from analyses group by status", "PENDING",
                "PROCESSING", "COMPLETED", "FAILED");

        // Mức rủi ro của mỗi cuộc gọi lấy từ lần phân tích hoàn tất mới nhất của nó.
        String latestRisk = """
                select distinct on (a.call_record_id) a.call_record_id, r.id as risk_id, r.risk_level
                  from analyses a join risk_results r on r.analysis_id = a.id
                 order by a.call_record_id, a.created_at desc
                """;
        Map<String, Long> risk = grouped("select risk_level, count(*) from (" + latestRisk + ") x group by risk_level",
                "LOW", "MEDIUM", "HIGH");

        List<IndicatorCount> indicators = jdbc.query("""
                select i.indicator_code, count(*) as calls
                  from (%s) x join risk_indicators i on i.risk_result_id = x.risk_id
                 group by i.indicator_code order by calls desc, i.indicator_code limit ?
                """.formatted(latestRisk),
                (rs, index) -> new IndicatorCount(rs.getString(1), rs.getLong(2)), TOP_INDICATORS);

        Map<String, Long> blacklist = new LinkedHashMap<>();
        blacklist.put("total", count("select count(*) from blacklist_numbers"));
        blacklist.put("active", count("select count(*) from blacklist_numbers where active"));
        Map<String, Long> reports = grouped("select status, count(*) from blacklist_reports group by status",
                "PENDING", "APPROVED", "REJECTED");
        Map<String, Long> patterns = new LinkedHashMap<>();
        patterns.put("total", count("select count(*) from phishing_patterns"));
        patterns.put("active", count("select count(*) from phishing_patterns where active"));

        List<DailyCount> daily = jdbc.query("""
                select d::date as day,
                       count(c.id) as calls,
                       count(*) filter (where x.risk_level = 'HIGH') as high,
                       count(*) filter (where x.risk_level = 'MEDIUM') as medium,
                       count(*) filter (where x.risk_level = 'LOW') as low,
                       count(c.id) filter (where x.risk_level is null) as unanalysed
                  from generate_series(?::date, ?::date, interval '1 day') d
                  left join call_records c on (c.created_at at time zone ?)::date = d::date
                  left join (%s) x on x.call_record_id = c.id
                 group by d order by d
                """.formatted(latestRisk),
                (rs, index) -> new DailyCount(rs.getObject("day", LocalDate.class), rs.getLong("calls"),
                        rs.getLong("high"), rs.getLong("medium"), rs.getLong("low"), rs.getLong("unanalysed")),
                java.sql.Date.valueOf(firstDay), java.sql.Date.valueOf(today), zone.getId());

        List<SuspectedNumber> suspected = jdbc.query("""
                select c.caller_number, count(*) as high_calls, count(distinct c.user_id) as users,
                       max(c.created_at) as last_call
                  from call_records c join (%s) x on x.call_record_id = c.id
                 where x.risk_level = 'HIGH' and c.caller_number is not null
                   and not exists (select 1 from blacklist_numbers b
                                    where b.phone_number = c.caller_number and b.active)
                 group by c.caller_number
                 order by high_calls desc, last_call desc limit ?
                """.formatted(latestRisk),
                (rs, index) -> new SuspectedNumber(rs.getString(1), rs.getLong(2), rs.getLong(3),
                        rs.getTimestamp(4).toInstant()), SUSPECTED_NUMBERS);

        return new Statistics(Instant.now().truncatedTo(ChronoUnit.SECONDS), period, zone.getId(), users, calls,
                analyses, risk, indicators, blacklist, reports, patterns, suspected, daily);
    }

    private long count(String sql, Object... args) {
        Long value = jdbc.queryForObject(sql, Long.class, args);
        return value == null ? 0 : value;
    }

    /** Đếm theo nhóm; các nhóm trong {@code keys} luôn có mặt trong kết quả, kể cả khi bằng 0. */
    private Map<String, Long> grouped(String sql, String... keys) {
        Map<String, Long> result = new LinkedHashMap<>();
        for (String key : keys) {
            result.put(key, 0L);
        }
        jdbc.query(sql, rs -> {
            result.put(rs.getString(1), rs.getLong(2));
        });
        return result;
    }
}
