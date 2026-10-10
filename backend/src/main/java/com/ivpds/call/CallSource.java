package com.ivpds.call;

/** Nguồn gốc file audio của cuộc gọi. */
public enum CallSource {
    /** Ghi âm trực tiếp trong ứng dụng. */
    RECORDED,
    /** Chọn file có sẵn trên thiết bị để tải lên. */
    UPLOADED,
    /** Cuộc gọi VoIP trong ứng dụng, được phân tích ngay khi đang diễn ra; audio do backend ghi lại. */
    LIVE
}
