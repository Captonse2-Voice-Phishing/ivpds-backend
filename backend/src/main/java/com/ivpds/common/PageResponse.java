package com.ivpds.common;

import java.util.List;
import java.util.function.Function;
import org.springframework.data.domain.Page;

/**
 * Cấu trúc phản hồi chung cho mọi API trả về danh sách có phân trang.
 *
 * @param items      các phần tử của trang hiện tại
 * @param page       số thứ tự trang (bắt đầu từ 0)
 * @param size       số phần tử mỗi trang
 * @param totalItems tổng số phần tử
 * @param totalPages tổng số trang
 */
public record PageResponse<T>(List<T> items, int page, int size, long totalItems, int totalPages) {

    /** Chuyển một trang kết quả của Spring Data thành phản hồi API, ánh xạ từng phần tử bằng {@code mapper}. */
    public static <S, T> PageResponse<T> of(Page<S> page, Function<S, T> mapper) {
        return new PageResponse<>(page.getContent().stream().map(mapper).toList(), page.getNumber(), page.getSize(),
                page.getTotalElements(), page.getTotalPages());
    }
}
