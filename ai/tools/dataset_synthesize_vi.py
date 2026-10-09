"""Sinh hội thoại điện thoại tổng hợp theo bối cảnh Việt Nam để bổ sung cho dữ liệu huấn luyện.

Cách dùng (chạy từ thư mục ``ai``):

    docker run --rm --network none -v "D:/Capstone2/ai:/work" -w /work --user root ivpds/ai:test \
        python -m tools.dataset_synthesize_vi

Ghi ``data/synthetic/vi_generated.jsonl``. Chạy lại luôn ra đúng cùng một file (hạt giống cố định).

ĐÂY LÀ DỮ LIỆU TỔNG HỢP, không phải cuộc gọi thật. Các kịch bản lừa đảo được viết theo những thủ đoạn mà
Bộ Công an và báo chí Việt Nam đã công bố (giả danh công an, ngân hàng, điện lực, thuế, bảo hiểm xã hội,
"làm nhiệm vụ", đầu tư, vay online, quà từ nước ngoài...). Các kịch bản bình thường cố ý chọn những cuộc
gọi dễ nhầm: ngân hàng thật, công an phường thật, shipper thật, người nhà chuyển tiền cho nhau.

Mỗi kịch bản là một chuỗi lượt lời; mỗi lượt có vài cách nói (thường là ba, ứng với ba mạch chuyện), một số
lượt có thể bị bỏ qua, các chi tiết (ngân hàng, số tiền, thời hạn...) được thay ngẫu nhiên. Vì cùng một kịch bản sinh ra nhiều hội thoại giống
nhau về ý, khi chia tập phải chia theo kịch bản (trường ``family``), không chia theo từng hội thoại.
"""

import json
import random
import sys
from pathlib import Path

OUT = Path("data/synthetic/vi_generated.jsonl")
SEED = 20261008
PER_FAMILY = 40

# ------------------------------------------------------------------------------------ chi tiết thay thế

FILLERS = {
    "bank": ["Vietcombank", "Techcombank", "BIDV", "Vietinbank", "Agribank", "MB", "ACB", "Sacombank", "VPBank",
             "TPBank"],
    "amt": ["hai triệu", "ba triệu rưỡi", "năm triệu", "tám triệu", "mười hai triệu", "mười lăm triệu",
            "hai mươi triệu", "ba mươi lăm triệu", "năm mươi triệu", "tám mươi triệu", "một trăm hai mươi triệu"],
    "small": ["hai trăm nghìn", "ba trăm năm mươi nghìn", "bốn trăm chín mươi nghìn", "sáu trăm nghìn",
              "chín trăm nghìn", "một triệu hai"],
    "big": ["hai trăm triệu", "ba trăm năm mươi triệu", "năm trăm triệu", "tám trăm triệu", "một tỷ hai"],
    "deadline": ["trong vòng hai tiếng", "trước năm giờ chiều nay", "trong hôm nay", "trong ba mươi phút nữa",
                 "trước mười hai giờ trưa", "ngay trong sáng nay"],
    "city": ["Hà Nội", "Đà Nẵng", "Thành phố Hồ Chí Minh", "Hải Phòng", "Cần Thơ", "Bình Dương"],
    "rank": ["đại úy", "thượng úy", "thiếu tá", "trung tá", "trung úy"],
    "pname": ["Hùng", "Quang", "Thắng", "Dũng", "Sơn", "Bình", "Tuấn", "Minh", "Long", "Hải"],
    "crime": ["rửa tiền", "buôn bán ma túy", "lừa đảo chiếm đoạt tài sản", "đánh bạc qua mạng",
              "mua bán tài khoản ngân hàng"],
    "telco": ["Viettel", "Vinaphone", "Mobifone"],
    "shop": ["Shopee", "Lazada", "Tiki", "TikTok Shop"],
    "item": ["nồi chiên không dầu", "đôi giày", "bộ mỹ phẩm", "tai nghe", "máy xay sinh tố", "cái áo khoác"],
    "prize": ["một xe máy SH", "một chiếc tivi", "một tủ lạnh", "một sổ tiết kiệm một trăm triệu",
              "một điện thoại iPhone"],
    "rel": ["con trai", "con gái", "em trai", "cháu", "chồng"],
    "app": ["Zalo", "Facebook", "Telegram"],
    "remote": ["TeamViewer", "UltraViewer", "AnyDesk"],
    "day": ["thứ hai", "thứ tư", "thứ sáu", "cuối tuần này", "sáng mai", "chiều mai"],
    "hour": ["tám giờ sáng", "chín rưỡi", "hai giờ chiều", "bốn giờ chiều", "bảy giờ tối"],
}

# Cách người gọi xưng hô với người nghe: (người gọi tự xưng, gọi người nghe, người nghe tự xưng).
PRONOUNS = [("em", "anh", "tôi"), ("em", "chị", "tôi"), ("tôi", "anh", "tôi"), ("tôi", "chị", "tôi"),
            ("cháu", "bác", "bác"), ("cháu", "cô", "cô"), ("em", "anh", "anh"), ("em", "chị", "chị")]
SPEAKER_STYLES = [("A", "B", "C"), ("Người gọi", "Người nghe", "Người gọi 2"), ("Bên gọi", "Bên nghe", "Bên gọi 2")]

# Phản ứng chung của người nghe, dùng lại ở nhiều kịch bản.
DOUBT = ["Sao lại thế được, {v} có làm gì đâu?", "Có nhầm không vậy?", "{V} chưa nghe chuyện này bao giờ.",
         "Chuyện này là sao, nói rõ hơn đi.", "Thật không đấy, nghe lạ quá."]
ASK = ["Vậy giờ {v} phải làm gì?", "Thế bây giờ làm thế nào?", "Rồi {v} cần làm gì tiếp?", "Giờ xử lý sao?"]
HESITATE = ["Để {v} hỏi người nhà đã.", "{V} ra trực tiếp làm có được không?", "Để {v} suy nghĩ đã.",
            "Sao không làm ở quầy mà phải qua điện thoại?", "{V} thấy không yên tâm lắm."]
AGREE = ["Vâng, để {v} làm.", "Dạ được.", "Ừ, {v} hiểu rồi.", "Vâng vâng, {v} làm ngay."]
THANKS = ["Vâng, cảm ơn nhé.", "Ok cảm ơn.", "Được rồi, cảm ơn nhiều.", "Vâng, chào nhé."]


def T(speaker: str, options: list[str], keep: float = 1.0) -> tuple[str, list[str], float]:
    """Một lượt lời: ai nói, các cách nói, và xác suất lượt này xuất hiện."""
    return speaker, options, keep


# ------------------------------------------------------------------------------- kịch bản lừa đảo

SCAM = {
    "giả công an điều tra": [
        T("C", ["Tôi là {rank} {pname}, cơ quan cảnh sát điều tra công an {city}. {Y} có phải chủ số điện thoại này không?",
                "Alo, đây là công an {city}. Tôi là {rank} {pname}, đang thụ lý một vụ án có liên quan đến {y}.",
                "{Y} nghe cho rõ, tôi là {rank} {pname} bên phòng cảnh sát hình sự, gọi để thông báo một việc nghiêm trọng."]),
        T("V", ["Dạ đúng, có chuyện gì vậy ạ?", "Vâng, {v} đây.", "Công an gọi {v} có việc gì ạ?"]),
        T("C", ["Số căn cước của {y} đứng tên một tài khoản dính đến đường dây {crime}. Chúng tôi đã có lệnh bắt tạm giam.",
                "Chúng tôi vừa bắt một nhóm {crime}, trong đó có tài khoản ngân hàng mở bằng tên {y}.",
                "{Y} đang bị tình nghi là đồng phạm trong vụ {crime}, hồ sơ đã chuyển viện kiểm sát."]),
        T("V", DOUBT, 0.8),
        T("C", ["Muốn chứng minh mình vô tội thì {y} phải hợp tác. Việc này là bí mật điều tra, không được nói với bất kỳ ai, kể cả người nhà.",
                "{Y} ra chỗ vắng người nói chuyện. Từ giờ không được tắt máy và không được kể với ai.",
                "Đây là án mật. {Y} mà tiết lộ cho gia đình là bị xử lý thêm tội cản trở điều tra."]),
        T("V", ASK, 0.7),
        T("C", ["{Y} chuyển toàn bộ tiền trong tài khoản sang tài khoản tạm giữ của cơ quan điều tra để kiểm tra nguồn tiền, sạch thì hoàn lại sau.",
                "{Y} ra ngân hàng rút sổ tiết kiệm, chuyển vào tài khoản thẩm tra tôi đọc. Xong việc chúng tôi trả lại đủ.",
                "{Y} kê khai số dư rồi chuyển hết sang tài khoản an toàn do chúng tôi quản lý {deadline}, nếu không lệnh bắt sẽ được thi hành."]),
    ],
    "giả ngân hàng rồi công an": [
        T("C", ["Dạ {m} là nhân viên ngân hàng {bank}. {Y} có mở một thẻ tín dụng ở {city} và đang nợ {amt}, {y} có biết không ạ?",
                "{M} gọi từ trung tâm thẻ {bank}. Hệ thống ghi nhận {y} có khoản vay {amt} quá hạn ba tháng.",
                "Chào {y}, {m} bên {bank}. Tài khoản của {y} vừa nhận {big} từ một tài khoản đang bị phong tỏa."]),
        T("V", ["Không, {v} chưa bao giờ mở thẻ ở đó.", "{V} làm gì có khoản nào như vậy.", "Chắc nhầm người rồi."]),
        T("C", ["Vậy là thông tin của {y} đã bị đánh cắp. {M} nối máy sang công an {city} để {y} trình báo ngay nhé.",
                "Trường hợp này có dấu hiệu hình sự, {m} chuyển cuộc gọi cho đồng chí cán bộ điều tra.",
                "{Y} giữ máy, {m} kết nối với cơ quan công an để họ hướng dẫn {y}."]),
        T("C2", ["Tôi là {rank} {pname}. Tên của anh chị nằm trong hồ sơ vụ án {crime}. Anh chị phải khai báo toàn bộ tài khoản ngân hàng.",
                 "{Rank} {pname} nghe. Chúng tôi xác định tài khoản của anh chị được dùng để {crime}. Hiện đã có lệnh phong tỏa tài sản.",
                 "Công an {city} đây. Vụ việc của anh chị rất nghiêm trọng, có thể bị bắt tạm giam để điều tra."]),
        T("V", DOUBT + ["{V} bị oan, xin cán bộ xem lại."]),
        T("C2", ["Anh chị chuyển hết tiền sang tài khoản tạm giữ để xác minh. Không được nói với người nhà, không được tắt máy.",
                 "Muốn được tại ngoại thì nộp tiền bảo lãnh {amt} vào tài khoản của viện kiểm sát {deadline}.",
                 "Anh chị cài ứng dụng của bộ công an theo đường link tôi gửi, đăng nhập các tài khoản ngân hàng vào đó. Giữ bí mật tuyệt đối."]),
    ],
    "giả công an phường cài ứng dụng": [
        T("C", ["Alo, tôi là cảnh sát khu vực công an phường. Tài khoản định danh điện tử của {y} bị lỗi, chưa đồng bộ dữ liệu dân cư.",
                "{M} là cán bộ công an quận phụ trách căn cước. Căn cước gắn chíp của {y} sai thông tin nơi thường trú.",
                "Chào {y}, tôi bên đội quản lý hành chính công an phường. Hồ sơ định danh mức hai của {y} bị trùng."]),
        T("V", ["{V} làm xong lâu rồi mà.", "Thế có phải lên phường không?", "Sai chỗ nào vậy?"]),
        T("C", ["Không cần lên phường, tôi gửi đường link qua {app}, {y} tải ứng dụng dịch vụ công về rồi cho phép tất cả các quyền.",
                "{Y} mở {app}, {m} gửi file cài đặt bản mới. Cài xong {y} quét khuôn mặt và nhập mật khẩu ngân hàng để liên kết.",
                "Giờ làm trực tuyến hết. {Y} bấm vào link tôi nhắn, cài phần mềm rồi đọc mã hiện trên màn hình cho tôi."]),
        T("V", HESITATE, 0.7),
        T("C", ["{Y} làm {deadline}, quá hạn là bị xử phạt hành chính và khóa tài khoản định danh.",
                "Không cập nhật thì tháng này {y} không giao dịch ngân hàng được đâu.",
                "Việc này bắt buộc theo quy định mới, {y} làm luôn kẻo bị phạt."]),
    ],
    "giả cơ quan thuế": [
        T("C", ["Chào {y}, {m} là cán bộ chi cục thuế. {Y} có một khoản hoàn thuế thu nhập cá nhân {small} chưa nhận.",
                "{M} gọi từ cơ quan thuế. Hộ kinh doanh của {y} được giảm thuế, bên {m} đang làm thủ tục hoàn tiền.",
                "Alo, {m} ở cục thuế. Mã số thuế của {y} đang bị cảnh báo nợ, cần cập nhật ngay."]),
        T("V", ["{V} chưa thấy thông báo gì.", "Vậy à, cần giấy tờ gì?", "Sao không gửi giấy về nhà?"]),
        T("C", ["{Y} tải ứng dụng thuế điện tử theo link {m} gửi qua {app}, đăng nhập bằng tài khoản ngân hàng để nhận tiền hoàn.",
                "{Y} đọc cho {m} số thẻ ATM và mã ngân hàng gửi về điện thoại để {m} làm lệnh chuyển tiền hoàn.",
                "{M} gửi đường link, {y} cài ứng dụng rồi cấp quyền truy cập, {m} xử lý từ xa cho."]),
        T("V", HESITATE, 0.6),
        T("C", ["Hôm nay là ngày cuối giải quyết, {y} làm luôn giúp {m}.",
                "Không làm {deadline} thì khoản hoàn bị hủy và {y} bị phạt chậm nộp.",
                "Đây là bản nội bộ nên không có trên kho ứng dụng, {y} cứ bấm link là được."]),
    ],
    "giả bảo hiểm xã hội": [
        T("C", ["Chào {y}, {m} là cán bộ bảo hiểm xã hội quận. {Y} được tăng lương hưu nhưng hồ sơ thiếu xác thực nên chưa chi.",
                "{M} gọi từ bảo hiểm xã hội thành phố. {Y} bị phát hiện trục lợi tiền bảo hiểm ở {city}, tổng số {amt}.",
                "Alo, {m} bên bảo hiểm xã hội. Tiền trợ cấp của {y} tháng này bị treo do sai thông tin tài khoản."]),
        T("V", DOUBT + ["Thiếu cái gì vậy?"]),
        T("C", ["{Y} đọc cho {m} số tài khoản, số căn cước và mã ngân hàng nhắn về máy để {m} cập nhật.",
                "Có người dùng căn cước của {y}. Việc đã chuyển công an, {m} nối máy để {y} làm việc, {y} không được tắt máy.",
                "{Y} cài ứng dụng bảo hiểm theo link {m} gửi, đưa mặt vào camera rồi nhập mật khẩu ngân hàng để nhận tiền."]),
        T("V", HESITATE, 0.7),
        T("C", ["Không cần hỏi ai đâu {y}, làm năm phút là xong, không là tháng này không có lương.",
                "{Y} đừng kể với con cháu, họ không hiểu thủ tục lại làm lỡ việc.",
                "{Y} làm {deadline} kẻo bị cắt chế độ."]),
    ],
    "giả điện lực": [
        T("C", ["Tôi gọi từ công ty điện lực. Nhà {y} nợ tiền điện hai kỳ, không thanh toán {deadline} là cắt điện.",
                "Điện lực thông báo, công tơ nhà {y} bị phát hiện can thiệp trái phép, mức truy thu là {amt}.",
                "{M} bên điện lực. Hệ thống chưa ghi nhận tiền điện tháng này của nhà {y}, chiều nay tổ thu sẽ tới cắt."]),
        T("V", ["Tháng nào {v} cũng đóng qua ngân hàng mà.", "{V} có đụng gì vào công tơ đâu.", "Để {v} kiểm tra lại đã."]),
        T("C", ["{Y} kết bạn {app} với nhân viên thu ngân, cài ứng dụng điện lực theo link được gửi rồi thanh toán trong đó.",
                "{Y} chuyển khoản vào tài khoản cá nhân của kế toán, tôi đọc số. Tài khoản công ty đang bảo trì.",
                "{Y} đọc số thẻ và mã OTP để tôi trừ nợ trực tiếp, khỏi bị cắt điện."]),
        T("V", HESITATE, 0.6),
        T("C", ["Không kịp đâu, xe cắt điện đang trên đường rồi, {y} làm ngay đi.",
                "Nếu {y} không nộp ngay thì hồ sơ chuyển công an xử lý tội trộm cắp điện.",
                "Chậm là phải đóng thêm phí đấu nối lại {small}."]),
    ],
    "giả nhà mạng khóa sim": [
        T("C", ["Chào {y}, {m} là nhân viên {telco}. Sim của {y} sẽ bị khóa hai chiều {deadline} vì chưa chuẩn hóa thông tin.",
                "Tổng đài {telco} xin thông báo, thuê bao của {y} dùng công nghệ cũ, phải nâng cấp lên 5G nếu không sẽ bị cắt liên lạc.",
                "{M} gọi từ {telco}. Số của {y} bị phản ánh nhắn tin lừa đảo nên sắp bị thu hồi."]),
        T("V", ["{V} đăng ký chính chủ rồi mà.", "Nâng cấp thì làm thế nào?", "{V} có nhắn gì cho ai đâu."]),
        T("C", ["{M} làm từ xa cho, {y} soạn tin theo cú pháp {m} đọc rồi đọc lại mã xác nhận nhà mạng gửi về.",
                "{Y} chụp hai mặt căn cước và ảnh {y} cầm căn cước gửi qua {app} số này, kèm mã OTP.",
                "{Y} bấm vào đường link {m} nhắn, nhập thông tin thuê bao và mã gửi về máy."]),
        T("V", HESITATE, 0.6),
        T("C", ["{Y} làm ngay kẻo sim bị khóa là mất hết danh bạ với tài khoản ngân hàng.",
                "Đây là kênh nghiệp vụ của {m}, {y} gửi liền cho kịp giờ.",
                "Chỉ còn ít phút nữa hệ thống khóa, {y} đọc mã nhanh giúp {m}."]),
    ],
    "giả ngân hàng lấy otp": [
        T("C", ["{M} là nhân viên ngân hàng {bank}. Thẻ của {y} vừa có giao dịch {amt} ở nước ngoài, {y} có thực hiện không ạ?",
                "Dạ {m} gọi từ {bank}. Tài khoản của {y} đang có người đăng nhập trên thiết bị lạ.",
                "{M} bên {bank}, {y} được nâng hạn mức thẻ tín dụng lên {big}, {m} làm thủ tục qua điện thoại luôn."]),
        T("V", ["Không, {v} không giao dịch gì cả.", "Thế à, giờ sao?", "Có phải ra quầy không?"]),
        T("C", ["{M} hủy giao dịch cho {y} ngay, {y} đọc mười sáu số trên thẻ, ngày hết hạn và ba số mặt sau.",
                "Hệ thống vừa gửi mã OTP về máy {y}, {y} đọc mã đó để {m} khóa giao dịch.",
                "{Y} đăng nhập ứng dụng ngân hàng, có mã kích hoạt gửi về thì đọc cho {m}."]),
        T("V", ["Ngân hàng không có sẵn thông tin của {v} à?", "Mã này đọc cho người khác có sao không?"] + HESITATE, 0.7),
        T("C", ["{M} cần đối chiếu để khóa đúng thẻ, {y} đọc nhanh kẻo tiền bị trừ tiếp.",
                "Mã chỉ có hiệu lực một phút, {y} đọc luôn giúp {m}.",
                "Nếu {y} không xác nhận thì ngân hàng không chịu trách nhiệm số tiền bị mất."]),
    ],
    "hoàn tiền sàn thương mại": [
        T("C", ["Chào {y}, {m} là nhân viên chăm sóc khách hàng {shop}. Đơn {item} của {y} bị lỗi nên bên {m} hoàn tiền gấp đôi.",
                "{M} bên bộ phận hoàn tiền {shop}. Lô {item} {y} mua bị thu hồi, công ty hoàn tiền và bồi thường thêm.",
                "Dạ {m} gọi từ {shop}, đơn hàng của {y} bị thất lạc, {m} làm thủ tục đền bù {small} cho {y}."]),
        T("V", ["Ừ đơn đó {v} có mua.", "Hoàn kiểu gì?", "Vậy hả, thế nhận tiền sao?"]),
        T("C", ["{M} gửi link qua {app}, {y} bấm vào rồi điền số thẻ ngân hàng và mã OTP là tiền về ngay.",
                "{Y} kết bạn {app} với kế toán. Để nhận bồi thường {y} thanh toán trước một đơn xác minh {small}, sau đó hệ thống hoàn cả gốc.",
                "{Y} mở ứng dụng ngân hàng, vào mục chuyển tiền rồi nhập dãy số {m} đọc vào ô số tiền, đó là mã nhận hoàn."]),
        T("V", ["Sao nhận tiền mà lại phải điền OTP?", "Phải trả trước à?"] + HESITATE, 0.7),
        T("C", ["Để hệ thống xác nhận {y} là chủ thẻ thôi ạ, {y} làm trong năm phút kẻo lệnh hoàn bị hủy.",
                "Chỉ là thao tác xác minh, năm phút sau tiền về lại tài khoản {y} liền.",
                "Bên {m} chỉ xử lý trong hôm nay, {y} phối hợp nhanh giúp {m}."]),
    ],
    "trúng thưởng": [
        T("C", ["Xin chúc mừng {y}, số điện thoại của {y} đã trúng giải nhất chương trình tri ân, phần quà là {prize}.",
                "Chào {y}, {m} bên siêu thị điện máy, {y} là khách hàng may mắn trúng {prize}.",
                "{M} là MC chương trình quay số, thuê bao của {y} vừa được chọn nhận {prize}."]),
        T("V", ["Thật không, {v} có tham gia gì đâu.", "Ôi thế à, nhận ở đâu?", "Có phải mất gì không?"]),
        T("C", ["Để nhận quà {y} nộp trước thuế trúng thưởng và phí hồ sơ {amt} vào tài khoản kế toán công ty.",
                "Quà giao tận nhà, {y} chỉ cần chuyển phí vận chuyển và bảo hiểm {small}, {m} nhắn số tài khoản qua {app}.",
                "{M} chuyển máy cho trưởng phòng kế toán. Theo quy định {y} đóng mười phần trăm giá trị giải trước khi nhận."]),
        T("V", ["Trừ thẳng vào giải không được à?", "Nhận quà mà cũng mất tiền sao?"] + HESITATE, 0.7),
        T("C", ["Quy định là phải nộp trước mới làm được hồ sơ, {y} chuyển {deadline} để giữ giải.",
                "Mai là hết hạn nhận thưởng, {y} chuyển sớm kẻo mất quà.",
                "Khoản này được hoàn lại khi {y} nhận giải, {y} yên tâm."]),
    ],
    "vay tiền online": [
        T("C", ["Chào {y}, {m} bên công ty tài chính. Hồ sơ vay {amt} của {y} đã được duyệt, lãi suất không phần trăm ba tháng đầu.",
                "{M} là chuyên viên tín dụng, bên {m} cho vay tín chấp không cần thế chấp, giải ngân trong ba mươi phút.",
                "Alo {y}, khoản vay {amt} qua ứng dụng của {y} đã có kết quả, {m} hướng dẫn nhận tiền."]),
        T("V", ["Nhanh vậy, bao giờ có tiền?", "{V} đang cần gấp.", "Thủ tục thế nào?"]),
        T("C", ["{Y} nhập sai số tài khoản nên khoản vay bị đóng băng, {y} nộp {small} để mở khóa hồ sơ.",
                "{Y} chuyển trước phí bảo hiểm khoản vay là mười phần trăm, {m} làm hợp đồng điện tử liền.",
                "{Y} chưa có lịch sử tín dụng nên phải chuyển {amt} chứng minh tài chính, giải ngân xong hoàn lại."]),
        T("V", ["{V} đang cần tiền mới đi vay mà.", "Trừ vào tiền vay không được sao?"] + HESITATE, 0.7),
        T("C", ["Không nộp thì công ty kiện {y} ra tòa vì vi phạm hợp đồng và {y} bị ghi nợ xấu.",
                "Hệ thống yêu cầu đóng phí trước mới ra tiền, {y} chuyển luôn nhé {m} đang giữ suất.",
                "{Y} ghi sai nội dung chuyển khoản rồi, phải nộp thêm {small} nữa mới mở được lệnh."]),
    ],
    "đầu tư có chim mồi": [
        T("C", ["Chào {y}, {m} là trợ lý của quỹ đầu tư quốc tế. Nhóm bên {m} có tín hiệu nội bộ, lãi mỗi ngày năm đến tám phần trăm.",
                "{M} tư vấn sàn tiền điện tử, gói ủy thác một tuần lãi ba mươi phần trăm, rút lúc nào cũng được.",
                "{Y} ơi, {m} bên sàn vàng trực tuyến, hôm nay mời {y} nghe chuyên gia đọc lệnh."]),
        T("C2", ["Tôi cũng là nhà đầu tư thôi, tôi vào {amt}, ba tuần rút về gấp rưỡi, rút nhanh lắm.",
                 "Chào anh chị, tôi là chuyên gia phân tích. Tỷ lệ thắng của nhóm là chín mươi lăm phần trăm, lỗ tôi chịu.",
                 "Tôi vừa nạp thêm sáng nay, đợt này lãi tốt, anh chị vào sớm đi."], 0.7),
        T("V", ["Lãi cao vậy có rủi ro không?", "{V} không rành mấy cái này.", "Có giấy phép không?"]),
        T("C", ["Bên {m} cam kết bảo toàn vốn. {Y} tải ứng dụng của quỹ, nạp thử {amt}, chiều rút lãi được luôn.",
                "{Y} không cần biết gì, chuyên gia đánh thay. {Y} chuyển tiền vào tài khoản sàn, {m} đổi sang USDT rồi vào lệnh.",
                "{Y} mở tài khoản rồi chuyển tiền cho {m} nạp hộ, gói thấp nhất {amt}, bao lỗ."]),
        T("V", HESITATE, 0.6),
        T("C", ["Hôm nay là phiên cuối mở tài khoản ưu đãi, {y} nạp {deadline} để {m} giữ suất.",
                "Nạp trong hôm nay được tặng thêm hai mươi phần trăm, mai là hết.",
                "Muốn rút lãi thì {y} phải nạp thêm {amt} để nâng hạng tài khoản."]),
    ],
    "làm nhiệm vụ cộng tác viên": [
        T("C", ["Chào bạn, mình bên phòng nhân sự {shop}, đang tuyển cộng tác viên làm tại nhà, mỗi ngày ba đến năm trăm nghìn.",
                "{M} tuyển người thả tim video và đánh giá sản phẩm, mỗi nhiệm vụ nhận mười đến ba mươi nghìn.",
                "Bạn ơi bên mình cần cộng tác viên chốt đơn ảo cho gian hàng, hoa hồng mười lăm phần trăm mỗi đơn."]),
        T("V", ["Công việc cụ thể là gì?", "Làm vậy có lương thật không?", "{V} làm thử mấy nhiệm vụ rồi, nhận được tiền thật."]),
        T("C", ["Bạn thanh toán trước đơn hàng để tăng doanh số, xong mỗi đơn bên mình hoàn tiền gốc kèm hoa hồng.",
                "Giờ mình đưa bạn vào nhóm nhiệm vụ nâng cao, bạn ứng {small} sẽ nhận lại gốc và lãi sau mười phút.",
                "Đơn đầu chỉ {small}, bạn chuyển vào tài khoản này rồi chụp màn hình gửi mình."]),
        T("C2", ["Em mới làm xong nè, chuyển hai triệu nhận về hai triệu sáu, uy tín lắm.",
                 "Mình rút được tiền rồi nha mọi người, làm tiếp đi.",
                 "Chị trưởng nhóm đây, cả nhóm đang chờ bạn hoàn thành đơn."], 0.6),
        T("V", ["Phải bỏ tiền của mình ra trước à?", "{V} chuyển rồi mà chưa thấy tiền về."] + HESITATE, 0.7),
        T("C", ["Do bạn thao tác sai nên tài khoản bị đóng băng, phải nạp thêm {amt} để mở khóa mới rút được.",
                "Bạn chuyển luôn đi, làm chậm là cả nhóm bị phạt, không ai rút được tiền.",
                "Phải làm đủ ba đơn liên tiếp mới rút được, đơn tiếp theo là {amt}."]),
    ],
    "người thân cấp cứu": [
        T("C", ["{Y} là phụ huynh của cháu đúng không, tôi là giáo viên ở trường. Cháu bị ngã chấn thương đầu, đang cấp cứu ở bệnh viện.",
                "Alo, tôi là điều dưỡng khoa cấp cứu. {Rel} của {y} bị tai nạn giao thông, đang rất nguy kịch.",
                "{M} là bạn cùng phòng của {rel} {y}, bạn ấy bị xe tông đang nằm viện."]),
        T("V", ["Trời ơi, có sao không?", "Đang ở bệnh viện nào?", "Cho {v} nói chuyện với bác sĩ."]),
        T("C2", ["Tôi là bác sĩ trực. Bệnh nhân xuất huyết não, cần mổ ngay, gia đình đóng tạm ứng {amt} thì mới tiến hành.",
                 "Người nhà nghe đây, bệnh nhân mất nhiều máu, phải chuyển {amt} tiền máu và vật tư ngay.",
                 "Bác sĩ đây, từng phút đều quý, gia đình chuyển viện phí trước rồi tới sau."], 0.7),
        T("C", ["{Y} chuyển ngay {amt} vào tài khoản của bác sĩ, tôi đọc số cho.",
                "Bệnh viện cần người nhà đóng tiền ngay, {y} chuyển khoản vào số tài khoản của khoa.",
                "Phải có tiền mới mổ được, {y} chuyển trước đi."]),
        T("V", ["{V} chạy tới ngay.", "Để {v} gọi người nhà trên đó qua."], 0.7),
        T("C", ["Không kịp đâu, {y} chuyển khoản luôn bây giờ, đừng gọi cho ai mất thời gian.",
                "Tới nơi thì trễ rồi, {y} chuyển trước cho kịp ca mổ.",
                "Chậm một chút là không cứu được, {y} làm ngay đi."]),
    ],
    "giả người quen mượn tiền": [
        T("C", ["Alo, tôi đây, tôi mới đổi số, lưu lại nhé. Đang có việc gấp cần nhờ.",
                "Em ơi anh giám đốc đây, anh đang họp với đối tác không nghe máy lâu được.",
                "Dì ơi con nè, con đang ở nước ngoài, điện thoại hư nên mượn số bạn gọi về."]),
        T("V", ["Ủa giọng nghe lạ vậy?", "Số này lạ quá.", "Có chuyện gì thế?"]),
        T("C", ["Đang bị cảm nên giọng khác. Chuyển giúp {amt} vào số tài khoản tôi nhắn, tối tôi gửi lại liền.",
                "Em chuyển gấp {amt} vào tài khoản đối tác anh nhắn qua {app}, chứng từ anh ký bù sau.",
                "Tài khoản con bị khóa, dì chuyển giùm con {amt} cho người ta trước, mai con gửi lại cả lãi."]),
        T("V", ["Nhiều vậy, để hỏi lại đã.", "Sao không chuyển từ tài khoản của mình?"] + HESITATE, 0.7),
        T("C", ["Đang rất gấp, chuyển luôn bây giờ được không, người ta chỉ chờ tới chiều.",
                "Em làm luôn đi, đừng báo ai kẻo lộ thông tin hợp đồng.",
                "Dì đừng nói với mẹ con nha, con muốn tạo bất ngờ."]),
    ],
    "lừa đặt cọc": [
        T("C", ["Phòng còn nha, hai mươi lăm mét có gác, giá rẻ nhất khu này.",
                "Vé Tết bên em còn đúng hai chỗ giá rẻ, {y} lấy không?",
                "Xe đó chính chủ, giá thấp hơn thị trường {amt} vì em cần tiền gấp."]),
        T("V", ["Tối {v} qua xem được không?", "Rẻ vậy, cho {v} đặt.", "{V} muốn xem trực tiếp trước."]),
        T("C", ["Sáng giờ nhiều người hỏi lắm, muốn giữ thì chuyển cọc {small} trước, ai cọc trước em để cho người đó.",
                "{Y} chuyển khoản ngay vào tài khoản em đọc, hệ thống giữ chỗ có mười phút thôi.",
                "Em đang ở xa, {y} chuyển cọc {amt} em gửi giấy tờ qua bưu điện."]),
        T("V", ["{V} chưa xem mà.", "Chuyển rồi bao giờ nhận?"] + HESITATE, 0.7),
        T("C", ["Đẹp như hình đó, {y} chuyển luôn đi không là em nhận cọc người khác.",
                "Hệ thống báo lỗi, {y} chuyển thêm một lần nữa để kích hoạt, tiền dư em hoàn sau.",
                "Còn đúng một suất cuối, {y} quyết nhanh giúp em."]),
    ],
    "quà từ nước ngoài": [
        T("C", ["Em yêu, anh đã gửi cho em một thùng quà từ nước ngoài, có trang sức và rất nhiều tiền mặt.",
                "Anh là kỹ sư đang làm ở giàn khoan, anh gửi toàn bộ tiền tiết kiệm về Việt Nam nhờ em giữ hộ.",
                "Bạn thân mến, tôi là bác sĩ quân y sắp nghỉ hưu, tôi gửi kiện hàng giá trị lớn cho bạn."]),
        T("V", ["Anh gửi nhiều vậy sao?", "Mình mới quen qua mạng mà.", "Rồi em phải làm gì?"]),
        T("C2", ["Tôi là nhân viên hải quan sân bay. Kiện hàng có ngoại tệ chưa khai báo, phải nộp thuế và tiền phạt {amt} để thông quan.",
                 "Công ty chuyển phát quốc tế đây, thùng hàng đã về kho, thanh toán phí lưu kho và bảo hiểm {amt} thì bên tôi giao.",
                 "Cán bộ hải quan đây. Máy soi phát hiện tiền mặt trong thùng, phải nộp {amt} tiền chứng nhận chống rửa tiền."]),
        T("V", ["{V} không có nhiều tiền vậy.", "{V} chuyển rồi sao chưa giao?"] + HESITATE),
        T("C2", ["Không nộp thì bị truy tố tội rửa tiền. Chuyển vào tài khoản cá nhân của thủ quỹ {deadline}.",
                 "Nộp thêm lần này là xong, hàng tới nơi là có cả đống tiền.",
                 "Quá hạn hôm nay hàng bị tịch thu và người nhận bị lập hồ sơ."]),
    ],
    "dịch vụ lấy lại tiền": [
        T("C", ["Chào {y}, {m} bên văn phòng luật. {M} biết {y} vừa bị lừa mất tiền, bên {m} nhận thu hồi trong bốn mươi tám giờ.",
                "Tôi là cán bộ phòng an ninh mạng, bên tôi vừa bắt nhóm lừa đảo, {y} nằm trong danh sách được hoàn tiền.",
                "{M} làm ở công ty công nghệ chuyên lấy lại tiền treo trên sàn, cam kết thu hồi."]),
        T("V", ["Lấy lại được thật à?", "May quá, {v} mất {amt}.", "Làm thế nào?"]),
        T("C", ["{Y} nộp phí dịch vụ mười phần trăm trước, bên kỹ thuật mới mở lệnh rút.",
                "{Y} cung cấp số tài khoản, tên đăng nhập và mật khẩu ngân hàng điện tử để chúng tôi hoàn tiền thẳng vào.",
                "{M} chuyển máy cho luật sư trưởng. {Y} đóng phí hồ sơ {small} là bên {m} làm ngay."]),
        T("V", ["{V} hết tiền rồi, lấy lại được rồi trừ không được sao?", "Cần cả mật khẩu à?"] + HESITATE, 0.7),
        T("C", ["Không được, phải nộp trước. {Y} vay tạm ai đó chuyển {deadline}.",
                "Để hệ thống đối chiếu thôi. Lát có mã về máy {y} đọc cho tôi, tiền về trong ba mươi phút.",
                "Tiền của {y} đã định vị được rồi, chậm là bọn nó tẩu tán mất."]),
    ],
    "giả hỗ trợ kỹ thuật": [
        T("C", ["Chào {y}, {m} là kỹ thuật viên trung tâm hỗ trợ {app}. Tài khoản của {y} bị báo cáo vi phạm, sẽ bị vô hiệu hóa sau hai mươi bốn giờ.",
                "{M} gọi từ trung tâm bảo mật. Máy tính của {y} đang gửi cảnh báo nhiễm mã độc về hệ thống bên {m}.",
                "Tổng đài hỗ trợ {app} đây, tài khoản của {y} đang bị đăng nhập ở nước ngoài."]),
        T("V", ["{V} có đăng gì đâu.", "Máy {v} vẫn chạy bình thường mà.", "Vậy là bị hack à?"]),
        T("C", ["{Y} đọc cho {m} mật khẩu và mã xác nhận vừa gửi về số điện thoại để {m} gỡ báo cáo.",
                "{Y} tải phần mềm {remote} rồi đọc ID và mật khẩu hiện trên màn hình để {m} quét giúp.",
                "{M} chuyển máy cho kỹ thuật viên cấp cao. {Y} cài ứng dụng hỗ trợ từ xa theo link {m} gửi."]),
        T("V", HESITATE + ["Có mất phí không?"], 0.6),
        T("C", ["{Y} mở luôn ứng dụng ngân hàng lên để {m} kiểm tra xem tài khoản có bị liên kết trái phép không.",
                "{Y} làm nhanh kẻo hệ thống khóa mất, hacker rút hết tiền đó.",
                "Trong lúc quét {y} chuyển tiền sang tài khoản an toàn {m} cung cấp cho chắc."]),
    ],
    "đe dọa tống tiền": [
        T("C", ["Thằng bạn mày vay bên tao {amt} rồi trốn, nó ghi số mày làm người bảo lãnh.",
                "Con mày đang ở trong tay tao. Muốn nó an toàn thì chuẩn bị {big}.",
                "Khoản vay qua ứng dụng của {y} đã quá hạn, tổng gốc lãi là {amt}."]),
        T("V", ["Tôi không biết gì chuyện đó.", "Anh là ai, cho tôi nói chuyện với con tôi.", "Tôi vay có ít thôi mà."]),
        T("C", ["Trong hôm nay không trả thì tao ghép ảnh mày gửi cho cả công ty với gia đình mày.",
                "Chuyển tiền vào số tài khoản tao nhắn trong vòng một tiếng. Báo công an là mày không gặp lại nó đâu.",
                "Không thanh toán {deadline} thì bên em gọi cho toàn bộ danh bạ và đăng hình lên mạng."]),
        T("V", ["Làm vậy là phạm pháp đó.", "Xin đừng làm hại nó.", "Cho tôi xin thêm vài ngày."], 0.8),
        T("C", ["Chuyển {small} trước vào tài khoản cá nhân này, không thì đừng trách.",
                "Đừng tắt máy, đừng gọi ai. Chậm một phút là tao không đảm bảo.",
                "Không có chuyện khất. Chuyển ngay, không qua ứng dụng."]),
    ],
    "giả shipper": [
        T("C", ["Alo {y}, em giao hàng đây, {y} có đơn {item} thu hộ {small} mà em gọi không ai nghe.",
                "Em shipper nè, đơn của {y} em để ở kho rồi, {y} chuyển khoản tiền hàng cho em nha.",
                "Em bên giao hàng nhanh, đơn {shop} của {y} bị sai địa chỉ nên em chưa giao được."]),
        T("V", ["{V} đang đi làm.", "Đơn nào nhỉ, {v} không nhớ.", "Vậy em gửi bảo vệ giúp."]),
        T("C", ["{Y} chuyển khoản {small} cho em rồi em gửi hàng ở bảo vệ.",
                "Em lỡ đăng ký nhầm {y} vào gói hội viên giao hàng, mỗi tháng trừ {amt}. Em gửi link để {y} hủy.",
                "{Y} bấm vào link em nhắn để xác nhận lại địa chỉ, nhập số thẻ để hoàn phí giao lại."]),
        T("V", ["Hội viên gì, {v} có đăng ký đâu?", "Sao phải nhập số thẻ?"] + HESITATE, 0.7),
        T("C", ["{Y} không hủy {deadline} là hệ thống tự trừ tiền trong tài khoản đó.",
                "{Y} vào link rồi đọc mã OTP cho nhân viên tổng đài là hủy được.",
                "Em gửi số tài khoản, {y} chuyển luôn giúp em, em còn đi giao đơn khác."]),
    ],
    "việc làm đóng phí": [
        T("C", ["Chào em, anh bên công ty xuất khẩu lao động. Đơn hàng đi Hàn lương bốn mươi triệu, bao đậu visa.",
                "{M} bên phòng tuyển dụng, công ty cần người nhập liệu tại nhà, lương mười lăm triệu không cần kinh nghiệm.",
                "Công ty mình tuyển nhân viên sân bay, lương cao, chỉ cần nộp hồ sơ online."]),
        T("V", ["{V} muốn làm lắm, chi phí sao?", "Cần bằng cấp gì không?", "{V} lên công ty nộp hồ sơ được không?"]),
        T("C", ["Trước mắt đặt cọc {amt} để giữ chỗ và làm hồ sơ, còn đúng hai suất cuối.",
                "Em chuyển {small} phí đồng phục và phí đào tạo, đi làm được hoàn lại.",
                "Văn phòng đang sửa, em chuyển khoản vào tài khoản cá nhân của anh, {deadline} nhé."]),
        T("V", HESITATE, 0.6),
        T("C", ["Không chuyển hôm nay là mất suất, bên anh đưa cho người khác.",
                "Phải đóng thêm phí khám sức khỏe {small} nữa thì hồ sơ mới được duyệt.",
                "Em cứ chuyển đi, hợp đồng anh gửi qua {app} sau."]),
    ],
    # --- Bổ sung đợt 4: lừa đảo xoay quanh học phí, người thân, nhà trọ và cuộc gọi tự động ---
    "giả giáo viên thu học phí": [
        T("C", ["Chào {y}, tôi là giáo viên chủ nhiệm của cháu. Nhà trường vừa đổi số tài khoản thu học phí kỳ này.",
                "{M} gọi từ phòng tài vụ của trường. Học phí của cháu đang bị treo, hệ thống báo chưa nhận được tiền.",
                "Phụ huynh ơi, lớp đang thu gấp quỹ và tiền học thêm, cô nhắn riêng từng nhà cho nhanh."]),
        T("V", ["Mọi khi {v} vẫn đóng qua ứng dụng của trường mà.", "{V} đóng rồi mà cô.", "Sao không báo trong nhóm lớp?"]),
        T("C", ["Ứng dụng đang bảo trì. {Y} chuyển {amt} vào tài khoản cá nhân của tôi {deadline}, tôi nộp hộ cho.",
                "{Y} chuyển lại {amt} vào số tài khoản tạm thu tôi đọc, rồi đọc mã ngân hàng gửi về để tôi xác nhận.",
                "{Y} chuyển {small} vào tài khoản của cô, đừng hỏi trong nhóm kẻo phụ huynh khác thắc mắc."]),
        T("V", HESITATE, 0.7),
        T("C", ["Không nộp hôm nay là cháu bị xóa tên khỏi danh sách lớp đấy.",
                "Quá hạn chiều nay cháu sẽ không được dự thi, {y} làm ngay giúp.",
                "{Y} chuyển luôn đi, tôi còn tổng hợp nộp cho nhà trường."]),
    ],
    "giả con xin tiền học": [
        T("C", ["Mẹ ơi con đây, điện thoại con hỏng nên con mượn số bạn gọi.",
                "Bố ơi con nè, con đổi số mới rồi, bố lưu lại nha.",
                "Dì ơi con là cháu dì đây, con nhắn mãi không được nên gọi bằng số thầy."]),
        T("V", ["Sao giọng con lạ thế?", "Có chuyện gì vậy con?", "Số này lạ quá."]),
        T("C", ["Con bị cảm. Con phải đóng học phí gấp trong chiều nay, mẹ chuyển {amt} vào tài khoản thầy giáo con nhắn nhé.",
                "Con đăng ký khóa học nước ngoài, phải nộp {amt} ngay hôm nay vào tài khoản trung tâm, bố chuyển giúp con.",
                "Con lỡ làm hỏng máy tính của bạn, phải đền {amt}, dì chuyển vào tài khoản bạn con giùm."]),
        T("V", ["Để mẹ gọi lại số cũ của con.", "Nhiều thế con?"] + HESITATE, 0.7),
        T("C", ["Mẹ đừng gọi số cũ, máy hỏng rồi. Mẹ chuyển luôn đi không con bị đình chỉ thi.",
                "Bố đừng nói với mẹ nhé, con sợ mẹ lo. Bố chuyển ngay giúp con.",
                "Dì chuyển liền đi, bạn con đang đứng chờ, con ngại lắm."]),
    ],
    "học bổng và hoàn học phí": [
        T("C", ["Chúc mừng em đã được chọn nhận học bổng toàn phần {amt} của quỹ khuyến học.",
                "Chào {y}, em bên trung tâm ngoại ngữ, bé nhà mình được hoàn {small} học phí theo chương trình ưu đãi.",
                "{M} là cán bộ bảo hiểm y tế học sinh, cháu nhà mình được hoàn tiền bảo hiểm {small}."]),
        T("V", ["{V} có đăng ký gì đâu.", "Vậy nhận thế nào?", "Sao không trả qua nhà trường?"]),
        T("C", ["Để nhận học bổng em nộp phí hồ sơ và thuế {small} vào tài khoản kế toán quỹ trong hôm nay.",
                "{Y} bấm vào đường link em gửi qua {app}, nhập số thẻ ngân hàng rồi đọc cho em mã OTP gửi về máy.",
                "{Y} tải ứng dụng theo link tôi gửi, cấp quyền rồi đăng nhập tài khoản ngân hàng để nhận tiền."]),
        T("V", ["Nhận tiền mà phải nộp tiền trước à?", "Sao hoàn tiền lại cần OTP?"] + HESITATE, 0.7),
        T("C", ["Hệ thống chọn ngẫu nhiên, em nộp sớm kẻo nhường suất cho người khác.",
                "Để xác nhận chủ thẻ thôi ạ, {y} làm trong năm phút kẻo hết lượt.",
                "Phải làm trong hôm nay, quá hạn là mất quyền lợi."]),
    ],
    "giả chủ trọ đổi tài khoản": [
        T("C", ["Chị là chủ nhà mới của em đây, chủ cũ bán nhà rồi.",
                "Anh là em trai chủ nhà, từ tháng này anh thu tiền phòng thay chị.",
                "Cô là người quản lý mới của dãy trọ, cô gọi báo đổi cách thu tiền."]),
        T("V", ["Sao chị chủ không báo em?", "Vậy hả anh?", "Cháu chưa nghe gì cả."]),
        T("C", ["Từ giờ em chuyển tiền trọ vào tài khoản chị nhắn, và chuyển trước ba tháng ngay hôm nay để giữ phòng.",
                "Em chuyển tiền tháng này với tiền cọc bổ sung {amt} vào số tài khoản của anh nhé.",
                "Cháu chuyển tiền nhà hai tháng vào tài khoản cô đọc, hôm nay luôn."]),
        T("V", HESITATE, 0.7),
        T("C", ["Không chuyển hôm nay là mai chị cho người khác thuê.",
                "Chị ấy bận, em chuyển luôn đi rồi anh gửi hợp đồng sau.",
                "Cháu không chuyển thì dọn đồ ra, có người đang chờ phòng."]),
    ],
    "cuộc gọi tự động": [
        T("C", ["Xin thông báo, quý khách có một bưu phẩm chưa nhận. Đây là lần thông báo cuối cùng.",
                "Công ty bảo hiểm xin chào, quý khách có một khoản bảo hiểm chưa nhận, đây là lần thông báo cuối cùng.",
                "Tổng đài xin thông báo, thuê bao của quý khách sẽ bị khóa sau hai giờ do chưa xác thực thông tin."]),
        T("C", ["Để biết thêm chi tiết vui lòng bấm phím chín để gặp nhân viên hỗ trợ.",
                "Vui lòng bấm phím sáu để được nhân viên hỗ trợ nhận tiền.",
                "Để tránh bị khóa, quý khách bấm phím một để được hướng dẫn."]),
        T("C", ["Nếu không liên hệ trong hôm nay, bưu phẩm sẽ bị chuyển cho cơ quan chức năng xử lý.",
                "Sau hôm nay khoản tiền sẽ bị hủy. Xin cảm ơn.",
                "Xin nhắc lại, bấm phím một để được hướng dẫn. Xin cảm ơn."], 0.7),
    ],
}

# ------------------------------------------------------------------------------ kịch bản bình thường

NORMAL = {
    "ngân hàng thật thông báo": [
        T("C", ["Dạ chào {y}, {m} gọi từ ngân hàng {bank} chi nhánh gần nhà {y}. Thẻ mới của {y} đã về, {y} ghé nhận trong giờ hành chính nhé.",
                "{M} là nhân viên {bank}, gọi nhắc kỳ thanh toán thẻ tín dụng của {y} đến hạn ngày hai mươi lăm.",
                "Chào {y}, {m} bên {bank}. Sổ tiết kiệm của {y} đến ngày đáo hạn vào {day}, {m} báo để {y} sắp xếp."]),
        T("V", ["Có cần mang gì không?", "Ừ {v} nhớ rồi.", "Vậy {v} ra quầy làm nhé."]),
        T("C", ["{Y} mang căn cước bản gốc thôi ạ. {M} không cần {y} cung cấp thông tin gì qua điện thoại.",
                "{Y} tự thanh toán trên ứng dụng hoặc tại quầy đều được ạ.",
                "Dạ {y} ra chi nhánh, nhân viên sẽ hướng dẫn. Ngân hàng không yêu cầu mã OTP hay mật khẩu qua điện thoại."]),
        T("V", THANKS),
    ],
    "khách gọi ngân hàng tra soát": [
        T("V", ["Alo ngân hàng phải không, {v} bị trừ tiền hai lần cho một giao dịch.",
                "{V} chuyển khoản nhầm người, giờ làm sao lấy lại?",
                "Thẻ của {v} bị nuốt ở cây ATM."]),
        T("C", ["Dạ {m} chuyển máy cho bộ phận tra soát hỗ trợ {y} ạ.",
                "Dạ {y} giữ máy, {m} nối sang chuyên viên xử lý."]),
        T("C2", ["Chào anh chị, em bên tra soát. Anh chị cho em biết ngày giao dịch và số tiền, em không cần mật khẩu hay mã OTP.",
                 "Dạ anh chị mang căn cước ra chi nhánh gần nhất điền đơn tra soát, ngân hàng xử lý trong bảy ngày làm việc.",
                 "Em ghi nhận rồi ạ. Anh chị tuyệt đối không cung cấp mã OTP cho bất kỳ ai gọi tới nhé."]),
        T("V", ["Hôm qua, khoảng {small}.", "Vậy mai {v} ra chi nhánh.", "Mất bao lâu thì có kết quả?"]),
        T("C2", ["Dạ kết quả sẽ được báo qua tin nhắn của ngân hàng ạ.", "Dạ trong vòng bảy ngày làm việc ạ.",
                 "Dạ em cảm ơn anh chị đã liên hệ."]),
    ],
    "công an phường thật": [
        T("C", ["Chào {y}, tôi là cảnh sát khu vực. Hồ sơ làm căn cước của {y} thiếu giấy khai sinh bản sao, {y} mang lên trụ sở bổ sung giúp.",
                "{M} ở công an phường, căn cước của {y} đã có, {y} ra phường nhận hoặc đăng ký nhận qua bưu điện.",
                "Công an phường mời {y} {day} lên trụ sở làm thủ tục đăng ký tạm trú."]),
        T("V", ["{Day} {v} lên được không?", "Có mất phí không?", "Cần mang gì theo?"]),
        T("C", ["Được, bộ phận một cửa làm từ bảy rưỡi. {Y} lên trực tiếp, chúng tôi không giải quyết qua điện thoại.",
                "{Y} mang giấy hẹn và căn cước cũ, không mất phí gì.",
                "{Y} lên trực tiếp nhé, không cần cài ứng dụng hay chuyển khoản gì cả."]),
        T("V", THANKS),
    ],
    "điện lực thật": [
        T("C", ["Điện lực xin thông báo, {day} từ tám giờ đến mười một giờ khu phố mình tạm ngừng cấp điện để bảo trì.",
                "{M} là nhân viên ghi chỉ số, hóa đơn tiền điện tháng này của nhà {y} là {small}.",
                "Điện lực gọi báo lịch thay công tơ định kỳ cho nhà {y} vào {day}, miễn phí."]),
        T("V", ["Vậy trưa có điện lại không?", "Ừ để {v} thanh toán trên điện thoại.", "Có cần người ở nhà không?"]),
        T("C", ["Khoảng mười một giờ có lại ạ, {y} xem lịch trên ứng dụng chăm sóc khách hàng.",
                "{Y} thanh toán qua ngân hàng hoặc cửa hàng tiện lợi như mọi tháng, hạn là ngày mười lăm.",
                "Dạ cần ạ, nhân viên có thẻ ngành và không thu tiền."]),
        T("V", THANKS),
    ],
    "nhà mạng thật tư vấn": [
        T("C", ["Chào {y}, {m} là nhân viên tổng đài {telco}. Thuê bao của {y} có thể đăng ký gói data chín mươi nghìn một tháng.",
                "{M} gọi từ {telco}, gói cước của {y} sắp hết hạn vào {day}, {y} có muốn gia hạn không ạ?",
                "Tổng đài {telco} xin nghe."]),
        T("V", ["Gói đó có gì?", "Thôi {v} đang dùng gói khác rồi.", "{V} muốn đổi sang eSIM thì làm sao?"]),
        T("C", ["Mỗi ngày bốn gigabyte và miễn phí gọi nội mạng dưới mười phút ạ.",
                "Dạ vâng, nếu cần {y} soạn tin đăng ký hoặc ra cửa hàng bất cứ lúc nào.",
                "{Y} mang căn cước ra cửa hàng {telco} gần nhất, phí hai mươi lăm nghìn đóng tại quầy. Bên {m} không đổi qua điện thoại."]),
        T("V", THANKS),
    ],
    "shipper thật": [
        T("C", ["Alo {y} ơi em giao hàng, đơn {shop} của {y} {small} thu hộ, {y} có nhà không?",
                "{Y} ơi em shipper, em đang ở cổng, {y} xuống nhận hàng giúp em.",
                "Em giao đơn {item} cho {y}, mười phút nữa em tới."]),
        T("V", ["{V} đi làm rồi, em gửi bảo vệ giúp.", "Đợi {v} năm phút.", "Đơn đó thanh toán rồi đúng không?"]),
        T("C", ["Dạ đơn thu hộ nên em cần thu tiền {y} ơi.", "Dạ đơn này trả trước rồi, {y} chỉ cần nhận thôi.",
                "Dạ vậy chiều em giao lại nha."]),
        T("V", ["Vậy để {v} chuyển khoản, em đọc số tài khoản đi.", "Ok {v} xuống liền.", "Ừ chiều năm giờ {v} có nhà."]),
        T("C", ["Dạ em nhắn số tài khoản qua tin nhắn, {y} chuyển xong em gửi hàng cho bảo vệ.", "Dạ em cảm ơn {y}.",
                "Dạ em chờ ở sảnh nha."], 0.8),
    ],
    "shop hoàn tiền thật": [
        T("C", ["Chào {y}, em là chủ shop. Cái {item} {y} đặt hết hàng nên em hủy đơn, tiền {y} đã chuyển em hoàn lại nhé.",
                "Shop gọi báo {item} của {y} bị lỗi, {y} gửi lại em đổi cái mới, phí ship em chịu.",
                "Em bên shop, đơn của {y} em giao chậm hai ngày, {y} thông cảm giúp em."]),
        T("V", ["Tiếc ghê. Em hoàn vào tài khoản lúc nãy là được.", "Ừ để {v} gửi lại.", "Không sao, cứ giao bình thường."]),
        T("C", ["Dạ em chuyển lại đúng tài khoản đó, {y} kiểm tra giúp em sau năm phút.",
                "Dạ bên vận chuyển sẽ tới lấy hàng vào {day} ạ.", "Dạ em cảm ơn {y} nhiều."]),
        T("V", ["Ừ {v} nhận được rồi, cảm ơn em.", "Ok em, cảm ơn.", "Ừ không sao đâu em."]),
    ],
    "gia đình chuyển tiền": [
        T("C", ["Mẹ ơi con hết tiền trọ rồi, mẹ gửi con {small} được không?",
                "Anh ơi tiền điện nước tháng này em đóng rồi, hết {small}.",
                "Bố ơi tuần sau con đóng học phí, bố chuyển cho con {amt} nha."]),
        T("V", ["Sao mới đầu tháng đã hết?", "Ừ để anh chuyển lại cho em.", "Hạn nộp bao giờ con?"]),
        T("C", ["Con đóng tiền học thêm mẹ ạ. Mẹ chuyển vào tài khoản của con như mọi lần nha.",
                "Còn tiền học của con em nộp luôn rồi.", "Dạ hạn là {day}, bố cứ từ từ."]),
        T("V", ["Ừ tối mẹ chuyển.", "Tổng bao nhiêu em nhắn anh.", "Ừ mai bố ra ngân hàng chuyển."]),
    ],
    "gia đình ba người": [
        T("C", ["Tết này nhà mình góp tiền sửa nhà cho ông bà nhé, tính hết khoảng {amt}.",
                "Chủ nhật về ăn giỗ ông nội nhé hai đứa.", "Hè này cả nhà đi biển không, bố mẹ tính đặt phòng."]),
        T("V", ["Con góp một phần, cuối tuần con chuyển.", "Dạ con về được, con mua trái cây.", "Đi chứ, con xin nghỉ phép."]),
        T("C2", ["Con góp ít hơn nha, con mới đóng tiền nhà.", "Con kẹt ca trực, con gửi tiền mua đồ cúng giúp con.",
                 "Con đi sau một ngày được không?"]),
        T("C", ["Được rồi, còn lại bố mẹ lo. Chuyển vào tài khoản của mẹ nhé.", "Không cần tiền bạc gì, rảnh thì về.",
                "Ừ, để mẹ đặt phòng rồi báo."]),
        T("V", ["Dạ, mẹ nhắn lại số tài khoản giúp con.", "Dạ vâng ạ.", "Ok mẹ."]),
    ],
    "bạn bè chia tiền": [
        T("C", ["Ê hôm qua ăn hết một triệu hai, chia bốn mỗi đứa ba trăm nha.",
                "Tối nay đá bóng bảy giờ, tiền sân chia đều nha.", "Mình mới đổi số điện thoại, bạn lưu lại nha."]),
        T("V", ["Ok, gửi số tài khoản đi tao chuyển.", "Tao đi, bao nhiêu một đứa?", "Ừ để mình lưu, dạo này khỏe không?"]),
        T("C", ["Tao nhắn {app} rồi đó. Cuối tuần đi chơi không?", "Sáu chục một đứa, xong chuyển cho tao.",
                "Khỏe. Chủ nhật họp lớp ở quán cũ, đi không?"]),
        T("V", ["Đi chứ, để tao hỏi vợ đã.", "Ok lát tao chuyển.", "Đi chứ, mấy giờ?"]),
    ],
    "trường học thông báo": [
        T("C", ["Chào {y}, em là cô chủ nhiệm. Em gọi trao đổi về việc học của con.",
                "Phụ huynh ơi, cháu bị trẹo chân nhẹ lúc đá bóng, đang nằm ở phòng y tế của trường, không sao đâu ạ.",
                "Nhà trường thông báo {day} họp phụ huynh lúc {hour}."]),
        T("V", ["Con có chuyện gì không cô?", "Cháu có nặng không?", "Vâng {v} sẽ tới."]),
        T("C", ["Con học tốt, chỉ hay quên bài tập. Học phí kỳ này trường thu qua ứng dụng của trường như mọi kỳ.",
                "Cô y tế băng rồi ạ, chiều {y} đón cháu sớm một chút là được.",
                "Dạ {y} xem thêm thông báo trong sổ liên lạc điện tử."]),
        T("V", ["Hạn nộp học phí đến bao giờ cô?", "Ba giờ {v} qua đón, cảm ơn cô.", "Vâng, cảm ơn cô."]),
        T("C", ["Dạ cuối tháng ạ.", "Dạ vâng ạ.", "Dạ vâng ạ."]),
    ],
    "phòng khám nhắc lịch": [
        T("C", ["Phòng khám xin nghe.", "Em gọi từ phòng khám, nhắc {y} lịch tái khám {day} lúc {hour}.",
                "Bệnh viện gọi báo kết quả xét nghiệm của {y} đã có."]),
        T("V", ["{V} muốn hỏi kết quả xét nghiệm hôm qua.", "Ừ {v} nhớ rồi.", "Kết quả sao rồi?"]),
        T("C", ["Dạ {y} chờ máy, em chuyển máy cho bác sĩ ạ.",
                "Dạ {y} nhớ nhịn ăn sáng trước khi tới nhé, em chuyển máy để bác sĩ dặn thêm.",
                "Dạ em chuyển máy cho bác sĩ trao đổi với {y} ạ."]),
        T("C2", ["Chào anh chị, kết quả bình thường, tuần sau tái khám, viện phí đóng tại quầy như lần trước.",
                 "Chào anh chị, lần này anh chị mang theo đơn thuốc cũ để tôi xem lại liều nhé.",
                 "Chỉ số hơi cao một chút, anh chị uống thuốc theo đơn cũ rồi tuần sau tái khám."]),
        T("V", ["Có cần mang thẻ bảo hiểm y tế không?"] + THANKS),
    ],
    "tuyển dụng thật": [
        T("C", ["Chào bạn, mình là nhân sự công ty. Mình mời bạn phỏng vấn lúc {hour} {day} tại văn phòng.",
                "Em qua thử việc được từ {day}, ca sáng sáu giờ đến mười hai giờ.",
                "Công ty báo bạn đã trúng tuyển, {day} bạn lên ký hợp đồng."]),
        T("V", ["Dạ được, cần chuẩn bị gì không?", "Lương thử việc tính sao?", "Dạ cảm ơn, cần mang giấy tờ gì?"]),
        T("C", ["Bạn mang laptop và bản in hồ sơ. Công ty không thu bất kỳ khoản phí nào.",
                "Hai mươi hai nghìn một giờ, cuối tuần trả. Em mang căn cước photo để làm hợp đồng.",
                "Bạn mang căn cước và sổ bảo hiểm nếu có, lên trực tiếp phòng nhân sự."]),
        T("V", THANKS),
    ],
    "thuê nhà thật": [
        T("C", ["Phòng còn nha em, hai mươi mét có ban công. Em qua xem lúc nào cũng được.",
                "Căn hộ hai phòng ngủ, sổ hồng đầy đủ, anh chị tới xem trực tiếp nhé.",
                "Nhà còn trống, {day} chị ở nhà cả ngày, em ghé xem."]),
        T("V", ["{Day} {v} qua xem được không?", "Nếu ưng thì đặt cọc thế nào?", "Giá có bớt không?"]),
        T("C", ["Được em. Xem ưng thì mình ký hợp đồng rồi mới cọc, chưa xem chị không nhận tiền.",
                "Mình ra phòng công chứng ký hợp đồng cọc, chuyển khoản tại đó có người làm chứng.",
                "Bớt được chút ít, em qua xem rồi nói chuyện."]),
        T("V", ["Vâng {hour} {v} qua.", "Ok vậy hẹn chị."] + THANKS),
    ],
    "bảo hiểm thật": [
        T("C", ["Chào {y}, {m} là tư vấn viên bảo hiểm đã hẹn {y} hôm trước. Hợp đồng của {y} đến kỳ đóng phí vào tháng sau.",
                "{M} gọi từ bảo hiểm xã hội quận, {y} đến nhận sổ hưu được rồi ạ.",
                "{M} bên bảo hiểm, hồ sơ bồi thường của {y} đã được duyệt, tiền sẽ về tài khoản {y} đã đăng ký trong hợp đồng."]),
        T("V", ["{V} muốn giảm mức phí được không?", "Người nhà đi nhận thay được không?", "Bao giờ có tiền?"]),
        T("C", ["Dạ được, {y} ra văn phòng ký giấy điều chỉnh. Bên {m} không thu tiền mặt qua tư vấn viên.",
                "Dạ được, mang giấy ủy quyền có xác nhận của phường và căn cước.",
                "Khoảng năm ngày làm việc ạ, {y} không cần làm gì thêm."]),
        T("V", ["Văn phòng làm việc đến mấy giờ?", "Giờ làm việc đến mấy giờ?", "Vâng, cảm ơn nhé."]),
        T("C", ["Dạ đến năm giờ chiều ạ.", "Dạ đến bốn rưỡi chiều các ngày trong tuần ạ.", "Dạ vâng ạ."]),
    ],
    "công việc ba người": [
        T("C", ["Hôm nay họp nhanh về hợp đồng. Kế toán nhận được tiền đặt cọc của đối tác chưa?",
                "Mọi người ơi tháng này phòng mình được thưởng dự án.", "Chiều nay ba giờ họp giao ban nhé."]),
        T("C2", ["Dạ bên họ chuyển {amt} sáng nay rồi anh.", "Kế toán sẽ chuyển cùng lương ngày mùng năm.",
                 "Dạ em chuẩn bị báo cáo rồi."]),
        T("V", ["Vậy em gửi hợp đồng bản cuối cho họ ký nhé.", "Tuyệt quá, bao giờ nhận?",
                "Em mới đổi tài khoản ngân hàng, em gửi lại số cho phòng kế toán nhé."]),
        T("C", ["Ừ, gửi trong hôm nay. Kế toán xuất hóa đơn cho họ.", "Em điền vào biểu mẫu nhân sự là được.",
                "Ừ, nhớ đúng giờ."]),
        T("C2", ["Dạ chiều em xuất.", "Dạ vâng."], 0.6),
    ],
    "kỹ thuật internet thật": [
        T("V", ["Mạng nhà {v} mất từ sáng, đèn modem nháy đỏ.", "Wifi nhà {v} chậm quá.",
                "Máy tính công ty của {v} báo hết dung lượng."]),
        T("C", ["Dạ {y} rút nguồn modem ba mươi giây rồi cắm lại giúp {m}.", "{Y} thử khởi động lại modem giúp {m}.",
                "Lát {m} qua bàn {y} dọn giúp, {y} lưu file đang làm lại trước nhé."]),
        T("V", ["{V} làm rồi vẫn không được.", "Vẫn chậm.", "Ừ qua đi."]),
        T("C", ["Vậy {m} tạo phiếu, kỹ thuật viên qua nhà {y} kiểm tra trong chiều nay, không thu phí.",
                "{M} sẽ cho người tới đổi modem mới vào {day}, miễn phí.", "Mười phút nữa {m} qua."]),
        T("V", THANKS),
    ],
    "đặt dịch vụ": [
        T("V", ["{V} muốn đặt bàn sáu người tối {day}.", "{V} muốn đặt hai phòng đôi cuối tuần.",
                "{V} hỏi giá xe máy bản mới."]),
        T("C", ["Dạ còn bàn ạ, {y} cho {m} xin tên và giờ tới.", "Dạ còn phòng, giá tám trăm nghìn một đêm.",
                "Dạ ba mươi sáu triệu, {m} chuyển máy cho bên trả góp tư vấn thêm."]),
        T("V", ["{Hour}, tên Minh.", "Thanh toán thế nào?", "Trả góp thì cần gì?"]),
        T("C", ["Dạ {m} giữ bàn tới giờ đó, không cần đặt cọc.", "{Y} thanh toán khi nhận phòng hoặc đặt trên trang web của khách sạn.",
                "{Y} mang căn cước đến cửa hàng làm hồ sơ, không cần đóng phí gì trước."]),
        T("V", THANKS),
    ],
    # --- Bổ sung đợt 4: chuyện tiền bạc và chuyện riêng thường ngày, không có ai ép ai làm gì ---
    "hỏi nhau về học phí": [
        T("C", ["Ê mày nộp học phí kỳ này chưa?", "Chị ơi trường bé nhà chị thu học phí chưa?",
                "Alo, học phí kỳ này tăng hả mày?"]),
        T("V", ["Chưa, tao định cuối tuần mới nộp.", "Thu rồi em, chị vừa đóng hôm qua.",
                "Ừ tăng mười phần trăm, tao đọc thông báo rồi."]),
        T("C", ["Hạn là {day} đó, nộp trễ bị khóa đăng ký môn.",
                "Bên em cô giáo nhắn đóng qua ứng dụng của trường, em chưa biết làm.",
                "Mệt ghê, tao phải xin thêm tiền nhà."]),
        T("V", ["Vậy mai tao lên phòng tài vụ nộp luôn.", "Dễ lắm, em vào mục thanh toán rồi quét mã là xong.",
                "Tao cũng vậy, tính đi làm thêm buổi tối."]),
        T("C", ["Ừ, tao nộp trên cổng sinh viên rồi, nhanh lắm.", "Vậy để tối em làm thử, cảm ơn chị.",
                "Có chỗ nào tuyển thì rủ tao với."]),
    ],
    "bố mẹ hỏi con về tiền học": [
        T("C", ["Con ơi học phí kỳ này trường thông báo bao nhiêu rồi?",
                "Con gái à, mẹ chuyển tiền học cho con rồi đấy, con kiểm tra xem.",
                "Dạo này học hành sao con, có thiếu tiền không?"]),
        T("V", ["Dạ {amt} mẹ ạ, hạn nộp cuối tháng.", "Dạ con thấy rồi mẹ.",
                "Dạ con vẫn còn, tháng trước mẹ cho con chưa tiêu hết."]),
        T("C", ["Ừ, mai mẹ ra ngân hàng chuyển vào tài khoản của con rồi con tự nộp nhé.",
                "Còn dư thì để tiêu vặt, đừng tiêu hoang.", "Thiếu thì nói mẹ nhé, đừng nhịn ăn."]),
        T("V", ["Dạ con cảm ơn mẹ.", "Dạ mai con lên trường nộp.", "Dạ con biết rồi mẹ."]),
        T("C", ["Nhớ giữ biên lai nghe con.", "Ăn uống đầy đủ vào nhé.", "Tết con về sớm nhé."], 0.8),
    ],
    "con xin tiền sinh hoạt": [
        T("C", ["Mẹ ơi tháng này tiền trọ tăng thêm ba trăm, chủ nhà mới báo.",
                "Bố ơi máy tính của con hỏng, sửa hết {small}.", "Bố à tuần sau con đóng tiền học thêm, {small}."]),
        T("V", ["Vậy tổng bao nhiêu hả con?", "Sao hỏng thế con?", "Sao tháng này cao thế?"]),
        T("C", ["Hai triệu tám mẹ ạ, tính cả điện nước.", "Hỏng ổ cứng, thợ bảo phải thay.",
                "Trung tâm thu luôn ba tháng bố ạ."]),
        T("V", ["Ừ, mẹ gửi thêm cho con năm trăm nữa.", "Thay đi con, để bố chuyển tiền cho.",
                "Được rồi, tối bố chuyển cho con."]),
        T("C", ["Dạ thôi mẹ, con đi dạy kèm cũng đủ rồi.", "Con có tiền làm thêm rồi, con báo để bố biết thôi.",
                "Dạ con cảm ơn bố."]),
    ],
    "bạn bè tâm sự": [
        T("C", ["Mày rảnh không tao kể chuyện này, tao với người yêu chia tay rồi.",
                "Dạo này tao chán lắm, công ty cắt giảm nhân sự, tao sợ mất việc.",
                "Tao buồn quá mày ơi, bố mẹ tao lại cãi nhau."]),
        T("V", ["Trời, sao vậy?", "Thật hả, mày làm tốt mà.", "Thôi đừng nghĩ nhiều."]),
        T("C", ["Hai đứa cãi nhau suốt, tao mệt quá.", "Ai biết được, sếp đang xem xét từng người.",
                "Tao biết nhưng mà áp lực lắm, không muốn về nhà."]),
        T("V", ["Thôi nín đi, tối qua nhà tao, tao nấu lẩu cho ăn.", "Có gì tao hỏi chỗ tao xem còn tuyển không.",
                "Cuối tuần đi cà phê với tao đi, tao bao."]),
        T("C", ["Ừ, may mà có mày.", "Cảm ơn mày, nói ra thấy nhẹ hẳn.", "Ừ, cảm ơn mày nha."]),
    ],
    "bạn bè vay và trả tiền": [
        T("C", ["Mày có sẵn năm trăm không cho tao mượn, cuối tháng tao trả.", "Tao trả mày {small} hôm trước mượn nhé.",
                "Hôm qua mày trả tiền cà phê hộ tao bao nhiêu để tao gửi lại?"]),
        T("V", ["Có, mày cần gấp không?", "Ừ, lúc nào cũng được mà.", "Có tám chục thôi, khỏi."]),
        T("C", ["Không gấp, mai gặp ở lớp mày đưa tao cũng được.",
                "Tao mới lĩnh lương, để tao chuyển khoản cho đỡ quên, mày gửi số tài khoản đi.",
                "Thôi để tao chuyển, không quen nợ."]),
        T("V", ["Ừ mai tao đưa tiền mặt nhé.", "Vẫn số cũ đó, tao nhắn lại cho.",
                "Ừ tùy mày, số tài khoản tao gửi trong nhóm rồi."]),
        T("C", ["Cảm ơn mày, tao đang kẹt tiền trọ.", "Ok tao chuyển ngay.", "Ok xong tao nhắn."], 0.8),
    ],
    "lương thưởng ở công ty": [
        T("C", ["Chị ơi tháng này lương về chưa chị?", "Anh ơi em xin ứng lương được không ạ, nhà em có việc.",
                "Em ơi chị gửi bảng chấm công rồi đó, em xem có sai gì không."]),
        T("V", ["Kế toán báo mùng năm mới chuyển em ạ.", "Em ứng bao nhiêu?", "Dạ em thấy thiếu một ngày tăng ca."]),
        T("C", ["Vậy hả, em tưởng hôm nay.", "Dạ {small} anh ạ.",
                "Vậy để chị bổ sung, tiền tăng ca cộng vào lương tháng này."]),
        T("V", ["Tháng này có thưởng dự án nữa đó.", "Được, em làm đơn gửi phòng nhân sự, mai kế toán chuyển.",
                "Dạ em cảm ơn chị."]),
    ],
    "chủ trọ thật nhắc tiền nhà": [
        T("C", ["Alo em ơi, tiền nhà tháng này em chuyển cho chị chưa?",
                "Cháu ơi tiền điện tháng này ba trăm hai, nước tám chục nha.",
                "Em ơi tháng sau chị tăng tiền phòng hai trăm, chị báo trước một tháng."]),
        T("V", ["Dạ em chưa chị, lương em mùng mười mới về.", "Dạ cháu chuyển cùng tiền nhà luôn ạ.",
                "Dạ vâng, em biết rồi chị."]),
        T("C", ["Ừ không sao, mùng mười chuyển cũng được.", "Ừ, vẫn tài khoản cũ nha cháu.",
                "Em có ở tiếp thì cuối tháng mình ký lại hợp đồng."]),
        T("V", ["Dạ em cảm ơn chị.", "Dạ vâng ạ.", "Dạ em ở tiếp chị ạ."]),
    ],
    "việc nhà và tiền chung": [
        T("C", ["Giỗ bố năm nay anh em mình mỗi người góp {small} nhé.", "Đám cưới em họ mình mừng bao nhiêu chị?",
                "Vợ ơi tiền điện tháng này bao nhiêu mà trừ tài khoản nhiều thế?"]),
        T("V", ["Ừ, em đưa chị dâu đi chợ, thiếu thì anh bù.", "Chị định đi hai triệu.",
                "Một triệu hai anh ạ, tháng này bật điều hòa suốt."]),
        T("C", ["Dạ để em chuyển cho chị luôn tối nay.", "Vậy em cũng đi hai triệu cho đều.",
                "Còn tiền học của con em đóng chưa?"]),
        T("V", ["Ừ, chủ nhật về sớm nhé.", "Chủ nhật mười giờ có mặt ở nhà hàng nha.", "Em đóng hôm qua rồi."]),
    ],
    "ngân hàng thật nhắc nợ": [
        T("C", ["Chào {y}, {m} gọi từ ngân hàng {bank}, khoản vay của {y} đến hạn thanh toán ngày mai, số tiền {small}.",
                "{M} bên công ty tài chính, thẻ tín dụng của {y} đã quá hạn năm ngày, {m} gọi để nhắc.",
                "Chào {y}, {m} là nhân viên chăm sóc khách hàng {bank}, {y} có muốn chuyển khoản vay sang trả góp không ạ?"]),
        T("V", ["Ừ {v} nhớ, mai {v} thanh toán trên ứng dụng.", "Cho {v} xin khất đến cuối tuần được không?",
                "Lãi suất thế nào em?"]),
        T("C", ["Dạ vâng, {y} thanh toán trên ứng dụng hoặc tại quầy đều được ạ.",
                "Dạ được, nhưng sẽ phát sinh phí chậm trả theo hợp đồng, {y} thanh toán sớm giúp ạ.",
                "Dạ một phẩy hai phần trăm một tháng, {y} ra chi nhánh ký giấy là được, không mất phí."]),
        T("V", THANKS),
    ],
    "tư vấn bán hàng thật": [
        T("C", ["Em chào {y}, em gọi từ công ty bảo hiểm, {y} có thời gian nghe em giới thiệu gói bảo hiểm sức khỏe không ạ?",
                "Alo {y} ạ, không biết {y} có nhu cầu mua đất nền ở ngoại thành không ạ?",
                "Chào {y}, bên em có khóa tiếng Anh giao tiếp buổi tối, {y} có quan tâm không ạ?"]),
        T("V", ["Hiện tại {v} chưa có nhu cầu em ạ.", "Giá cả thế nào em?",
                "{V} đang bận, em gửi thông tin qua tin nhắn nhé."]),
        T("C", ["Dạ vâng, khi nào {y} cần thì liên hệ em nhé, em cảm ơn {y}.",
                "Dạ em mời {y} qua văn phòng xem trực tiếp rồi mình trao đổi ạ.",
                "Dạ em gửi ngay, {y} xem rồi có gì gọi lại em ạ."]),
        T("V", THANKS, 0.7),
    ],
    "tự kể chuyện giao dịch của mình": [
        T("C", ["Hôm nay tôi đăng nhập ngân hàng và nhập mã OTP của tôi để chuyển tiền nhà.",
                "Anh cho em số tài khoản để em chuyển tiền hàng cho anh.",
                "Tôi vừa ra cây ATM rút tiền rồi nộp học phí cho con.",
                "Em gửi số tài khoản đi để chị chuyển tiền cọc.",
                "Tôi quên mật khẩu ứng dụng ngân hàng nên phải ra quầy làm lại.",
                "Mình mới chuyển khoản trả tiền điện qua ứng dụng xong.",
                "Cho anh xin số tài khoản, anh trả tiền sửa xe.",
                "Tôi tự nhập mã xác thực trên điện thoại của tôi là xong."]),
    ],
}

# Kịch bản dành riêng cho validation: model không được thấy chúng khi huấn luyện.
VALIDATION_FAMILIES = {
    "giả nhà mạng khóa sim", "lừa đặt cọc", "dịch vụ lấy lại tiền", "nhà mạng thật tư vấn", "thuê nhà thật",
    "shop hoàn tiền thật", "giả chủ trọ đổi tài khoản", "chủ trọ thật nhắc tiền nhà",
}



# --------------------------------------------------------------- cặp kịch bản cùng chủ đề (đợt 5)
# Mỗi cặp có phần mở đầu DÙNG CHUNG (cùng tổ chức, cùng vấn đề, cùng từ ngữ) rồi rẽ hai hướng: bản hợp pháp
# và bản lừa đảo. Hai bản chỉ khác nhau ở hành vi: bản lừa đảo đòi mã, đòi chuyển tiền, ép cài ứng dụng, hối
# thúc, bắt giữ bí mật; bản hợp pháp mời ra quầy, dùng kênh chính thức và không đòi thông tin bí mật.
# Mục đích: model phải dựa vào việc người gọi yêu cầu gì, không dựa vào chủ đề hay từ khóa.

PAIRS = {
    "ngân hàng báo giao dịch lạ": {
        "shared": [
            T("C", ["Chào {y}, {m} gọi từ ngân hàng {bank}. Thẻ của {y} vừa phát sinh một giao dịch {amt} mà hệ thống đánh dấu là bất thường.",
                    "{M} là nhân viên {bank}. Tài khoản của {y} vừa có một lần đăng nhập từ thiết bị lạ.",
                    "Dạ {m} bên {bank}, hệ thống ghi nhận tài khoản của {y} có giao dịch đáng ngờ lúc sáng nay."]),
            T("V", ["{V} không thực hiện giao dịch nào cả.", "Vậy à, giờ phải làm sao?", "Có mất tiền không em?"]),
        ],
        "legit": [
            T("C", ["Dạ ngân hàng đã tạm khóa thẻ để bảo vệ {y}. {Y} mang căn cước ra chi nhánh gần nhất để mở lại thẻ ạ.",
                    "Dạ giao dịch đã bị chặn rồi ạ. {Y} có thể tự đổi mật khẩu trong ứng dụng, {m} không cần {y} cung cấp gì qua điện thoại.",
                    "Dạ {y} yên tâm, tiền vẫn an toàn. {Y} gọi lại số tổng đài in ở mặt sau thẻ để được tra soát ạ."]),
            T("V", ["Có cần đọc mã gì cho em không?", "Mai {v} ra chi nhánh được không?", "Vâng để {v} gọi tổng đài."]),
            T("C", ["Dạ không ạ, ngân hàng không bao giờ hỏi mã OTP hay mật khẩu qua điện thoại.",
                    "Dạ được ạ, chi nhánh làm việc giờ hành chính.", "Dạ vâng, {m} cảm ơn {y}."]),
        ],
        "scam": [
            T("C", ["Để hủy giao dịch {y} đọc cho {m} mã OTP vừa gửi về máy.",
                    "{M} cần xác minh chủ thẻ, {y} đọc số thẻ, ngày hết hạn và ba số mặt sau.",
                    "{Y} chuyển toàn bộ số dư sang tài khoản an toàn {m} cung cấp để tránh bị trừ tiếp."]),
            T("V", HESITATE, 0.7),
            T("C", ["Mã chỉ có hiệu lực một phút, {y} đọc ngay kẻo tiền bị trừ tiếp.",
                    "Nếu {y} không xác minh ngay thì ngân hàng không chịu trách nhiệm số tiền bị mất.",
                    "{Y} làm luôn bây giờ, đừng tắt máy."]),
        ],
    },
    "công an liên hệ": {
        "shared": [
            T("C", ["Chào {y}, tôi là cán bộ công an phường. Tôi gọi về một việc liên quan đến giấy tờ của {y}.",
                    "Tôi là cán bộ công an quận, cơ quan đang xác minh một hồ sơ có tên {y}.",
                    "Công an phường đây, chúng tôi cần làm việc với {y} về một trình báo có liên quan."]),
            T("V", ["Dạ có việc gì vậy ạ?", "{V} có làm gì đâu.", "Việc gì thế cán bộ?"]),
        ],
        "legit": [
            T("C", ["Chúng tôi đã gửi giấy mời, {y} mang giấy mời và căn cước lên trụ sở vào {day} để làm việc trực tiếp.",
                    "Việc này không trao đổi qua điện thoại được. {Y} sắp xếp lên trụ sở công an phường trong giờ hành chính.",
                    "{Y} cứ lên bộ phận một cửa, cán bộ trực sẽ hướng dẫn, không mất phí gì."]),
            T("V", ["{Day} {v} lên được không?", "Có phải nộp gì không?", "Vâng {v} sẽ lên."]),
            T("C", ["Được, cơ quan không yêu cầu chuyển tiền hay cài ứng dụng gì qua điện thoại.",
                    "Không nộp gì cả, {y} chỉ cần có mặt.", "Vâng, hẹn {y} ở trụ sở."]),
        ],
        "scam": [
            T("C", ["{Y} đang liên quan đến một đường dây {crime}. Đây là án mật, {y} không được nói với ai.",
                    "Căn cước của {y} bị dùng để mở tài khoản {crime}. Chúng tôi đã có lệnh bắt tạm giam.",
                    "{Y} phải hợp tác ngay qua điện thoại, không cần lên trụ sở, và giữ bí mật với người nhà."]),
            T("V", DOUBT, 0.7),
            T("C", ["Để chứng minh trong sạch {y} chuyển toàn bộ tiền sang tài khoản tạm giữ của cơ quan điều tra.",
                    "{Y} cài ứng dụng của bộ công an theo đường link tôi gửi rồi đăng nhập các tài khoản ngân hàng.",
                    "{Y} nộp {amt} tiền bảo lãnh {deadline}, nếu không lệnh bắt sẽ được thi hành."]),
        ],
    },
    "cơ quan thuế liên hệ": {
        "shared": [
            T("C", ["Chào {y}, {m} là cán bộ chi cục thuế, {m} gọi về hồ sơ quyết toán thuế của {y}.",
                    "{M} bên cơ quan thuế, hệ thống ghi nhận tờ khai của {y} còn thiếu thông tin.",
                    "Chi cục thuế xin thông báo, {y} có một khoản thuế cần được xử lý trong kỳ này."]),
            T("V", ["Thiếu gì vậy em?", "{V} nộp đủ rồi mà.", "Vậy {v} phải làm gì?"]),
        ],
        "legit": [
            T("C", ["{Y} đăng nhập cổng thuế điện tử chính thức như mọi lần để bổ sung, hoặc mang hồ sơ đến chi cục.",
                    "Hạn nộp là cuối tháng, {y} nộp qua ngân hàng hoặc tại kho bạc như thường lệ.",
                    "{Y} đến bộ phận một cửa của chi cục, cán bộ sẽ hướng dẫn trực tiếp."]),
            T("V", ["Có cần cài thêm gì không?", "Vâng để {v} xem lại.", "{Day} {v} lên được không?"]),
            T("C", ["Dạ không cần cài gì thêm, {m} cũng không gửi đường link nào cho {y} đâu ạ.",
                    "Dạ vâng, có gì {y} gọi số tổng đài của ngành thuế.", "Dạ được ạ."]),
        ],
        "scam": [
            T("C", ["{Y} tải ứng dụng thuế theo đường link {m} gửi qua {app}, cấp hết các quyền rồi đăng nhập tài khoản ngân hàng.",
                    "{Y} đọc cho {m} số thẻ và mã ngân hàng gửi về máy để {m} làm lệnh hoàn thuế.",
                    "{Y} chuyển {small} phí xử lý hồ sơ vào tài khoản cá nhân của {m} để được ưu tiên."]),
            T("V", HESITATE, 0.7),
            T("C", ["Hôm nay là ngày cuối, không làm ngay {y} sẽ bị phạt và cưỡng chế tài khoản.",
                    "Bản này là bản nội bộ nên không có trên kho ứng dụng, {y} cứ bấm link.",
                    "{Y} làm {deadline} kẻo khoản hoàn bị hủy."]),
        ],
    },
    "điện lực báo tiền điện": {
        "shared": [
            T("C", ["Chào {y}, {m} bên điện lực, hệ thống báo hóa đơn tiền điện tháng này của nhà {y} chưa được thanh toán.",
                    "Điện lực gọi về tiền điện của hộ nhà {y}, hiện còn một kỳ chưa ghi nhận.",
                    "{M} là nhân viên điện lực, nhà {y} có một hóa đơn {small} đang quá hạn."]),
            T("V", ["Tháng nào {v} cũng đóng qua ngân hàng mà.", "Vậy à, để {v} kiểm tra.", "Hạn đến bao giờ?"]),
        ],
        "legit": [
            T("C", ["Có thể ngân hàng trừ chậm ạ. {Y} kiểm tra trên ứng dụng chăm sóc khách hàng của điện lực rồi thanh toán như mọi tháng.",
                    "Hạn thanh toán còn đến ngày hai mươi, {y} đóng qua ngân hàng hoặc cửa hàng tiện lợi đều được.",
                    "{Y} cứ thanh toán theo cách vẫn dùng, nếu đã trả rồi thì bỏ qua cuộc gọi này giúp {m}."]),
            T("V", ["Vâng để {v} xem.", "Có bị cắt điện không?", "Ừ cảm ơn em."]),
            T("C", ["Dạ {m} chỉ nhắc thôi ạ, {m} không thu tiền qua điện thoại.", "Dạ chưa đâu ạ, còn trong hạn.", "Dạ {m} chào {y}."]),
        ],
        "scam": [
            T("C", ["{Y} kết bạn {app} với nhân viên thu ngân, cài ứng dụng theo link được gửi rồi thanh toán trong đó.",
                    "{Y} chuyển khoản ngay vào tài khoản cá nhân của kế toán, tài khoản công ty đang bảo trì.",
                    "{Y} đọc số thẻ và mã OTP để {m} trừ nợ trực tiếp."]),
            T("V", HESITATE, 0.7),
            T("C", ["Không kịp đâu, tổ cắt điện đang trên đường, {y} làm ngay đi.",
                    "Không thanh toán {deadline} thì cắt điện và phạt {small}.",
                    "{Y} chuyển luôn kẻo phải đóng phí đấu nối lại."]),
        ],
    },
    "nhà mạng báo thông tin thuê bao": {
        "shared": [
            T("C", ["Chào {y}, {m} là nhân viên {telco}. Thông tin thuê bao của {y} chưa khớp với dữ liệu dân cư.",
                    "Tổng đài {telco} thông báo thuê bao của {y} cần được cập nhật giấy tờ.",
                    "{M} gọi từ {telco}, số của {y} đang nằm trong danh sách cần chuẩn hóa thông tin."]),
            T("V", ["{V} đăng ký chính chủ rồi mà.", "Cập nhật thế nào em?", "Không cập nhật thì sao?"]),
        ],
        "legit": [
            T("C", ["{Y} mang căn cước ra cửa hàng {telco} gần nhất, hoặc tự cập nhật trong ứng dụng chính thức của nhà mạng.",
                    "{Y} ra điểm giao dịch, nhân viên làm trong mười phút, không mất phí.",
                    "Hạn cập nhật đến cuối tháng sau, {y} sắp xếp ra cửa hàng lúc nào tiện."]),
            T("V", ["Làm qua điện thoại được không?", "Vâng để {v} ra cửa hàng.", "Có mất tiền không?"]),
            T("C", ["Dạ không ạ, bên {m} không nhận giấy tờ hay mã xác nhận qua điện thoại.", "Dạ {m} cảm ơn {y}.", "Dạ miễn phí ạ."]),
        ],
        "scam": [
            T("C", ["{M} làm từ xa cho, {y} đọc mã xác nhận nhà mạng vừa gửi về máy.",
                    "{Y} chụp hai mặt căn cước và ảnh cầm căn cước gửi qua {app} số này, kèm mã OTP.",
                    "{Y} bấm vào đường link {m} nhắn rồi nhập thông tin và mã gửi về máy."]),
            T("V", HESITATE, 0.7),
            T("C", ["Sim sẽ bị khóa hai chiều {deadline}, {y} làm ngay kẻo mất số.",
                    "Chỉ còn ít phút nữa hệ thống khóa, {y} đọc mã nhanh giúp {m}.",
                    "Không làm bây giờ là thuê bao bị thu hồi."]),
        ],
    },
    "hoàn tiền đơn hàng": {
        "shared": [
            T("C", ["Chào {y}, {m} bên chăm sóc khách hàng {shop}. Đơn {item} của {y} có lỗi nên bên {m} sẽ hoàn tiền.",
                    "{M} gọi từ {shop}, đơn hàng của {y} bị hủy do hết hàng và tiền sẽ được hoàn lại.",
                    "Dạ {m} bên {shop}, sản phẩm {y} mua nằm trong đợt thu hồi nên công ty hoàn tiền."]),
            T("V", ["Hoàn kiểu gì em?", "Bao giờ nhận được?", "Vậy {v} cần làm gì?"]),
        ],
        "legit": [
            T("C", ["Tiền sẽ tự hoàn về phương thức {y} đã thanh toán trong ba đến năm ngày, {y} không cần làm gì thêm.",
                    "{Y} xem trạng thái hoàn tiền ngay trong ứng dụng {shop}, mục đơn hàng.",
                    "Bên {m} đã tạo lệnh hoàn, {y} chỉ cần chờ thông báo trong ứng dụng."]),
            T("V", ["Có cần cung cấp số thẻ không?", "Vâng cảm ơn em.", "Chưa thấy thì hỏi ở đâu?"]),
            T("C", ["Dạ không cần ạ, bên {m} không hỏi số thẻ hay mã OTP.", "Dạ {m} cảm ơn {y}.", "Dạ {y} nhắn trong mục trợ giúp của ứng dụng ạ."]),
        ],
        "scam": [
            T("C", ["{Y} bấm vào đường link {m} gửi qua {app}, điền số thẻ và mã OTP là tiền về ngay.",
                    "Để nhận tiền {y} thanh toán trước một đơn xác minh {small}, sau đó hệ thống hoàn cả gốc.",
                    "{Y} mở ứng dụng ngân hàng, nhập dãy số {m} đọc vào ô số tiền rồi đọc mã OTP cho {m}."]),
            T("V", HESITATE, 0.7),
            T("C", ["{Y} làm trong năm phút kẻo lệnh hoàn bị hủy.", "Chỉ xử lý trong hôm nay thôi ạ.",
                    "Chỉ là thao tác xác minh, {y} làm nhanh giúp {m}."]),
        ],
    },
    "bưu phẩm chưa nhận": {
        "shared": [
            T("C", ["Chào {y}, bưu điện gọi báo {y} có một bưu phẩm chưa nhận.",
                    "{M} bên bưu cục, có một thư bảo đảm gửi cho {y} mà phát hai lần chưa được.",
                    "Bưu điện xin thông báo {y} có một kiện hàng đang lưu tại bưu cục."]),
            T("V", ["Ai gửi vậy em?", "{V} không đặt gì cả.", "Nhận ở đâu?"]),
        ],
        "legit": [
            T("C", ["{Y} mang căn cước ra bưu cục trong giờ hành chính để nhận, bên {m} giữ bảy ngày.",
                    "Trên phiếu ghi là thư từ ngân hàng, {y} ra bưu cục ký nhận là được.",
                    "{Y} muốn phát lại thì cho {m} xin khung giờ có người ở nhà."]),
            T("V", ["Có mất phí không?", "Mai {v} ra nhận.", "Chiều mai sau năm giờ nhé."]),
            T("C", ["Dạ không mất phí ạ.", "Dạ vâng.", "Dạ {m} ghi lại rồi ạ."]),
        ],
        "scam": [
            T("C", ["Bưu phẩm chứa giấy tờ giả nên đã bị công an tạm giữ, {m} nối máy để {y} làm việc với cán bộ điều tra.",
                    "Kiện hàng bị hải quan giữ, {y} chuyển {amt} tiền thuế và phí thông quan vào tài khoản này để nhận.",
                    "Đây là lần thông báo cuối, {y} bấm phím chín để gặp nhân viên xử lý ngay."]),
            T("V", DOUBT, 0.7),
            T("C", ["{Y} không được tắt máy và không kể với ai cho đến khi làm việc xong.",
                    "Không nộp {deadline} là {y} bị lập hồ sơ xử lý.",
                    "{Y} đọc số căn cước và số tài khoản ngân hàng để đối chiếu ngay."]),
        ],
    },
    "nhà trường báo việc của con": {
        "shared": [
            T("C", ["Chào phụ huynh, tôi là giáo viên của cháu, tôi gọi về việc của cháu ở trường hôm nay.",
                    "Phụ huynh ơi, cô giáo của bé đây, bé hôm nay có chút việc ở lớp.",
                    "Tôi gọi từ trường của cháu, có việc cần báo với gia đình."]),
            T("V", ["Cháu có chuyện gì vậy cô?", "Con tôi sao rồi?", "Dạ cô nói đi ạ."]),
        ],
        "legit": [
            T("C", ["Cháu bị sốt nhẹ, đang nằm ở phòng y tế, phụ huynh thu xếp đón cháu sớm nhé.",
                    "Cháu quên chưa nộp bản đăng ký ngoại khóa, phụ huynh nhắc cháu mai mang đi.",
                    "Học phí kỳ này trường vẫn thu qua ứng dụng như mọi kỳ, hạn đến cuối tháng."]),
            T("V", ["Vâng tôi qua đón ngay.", "Vâng để tôi nhắc cháu.", "Vâng tôi sẽ đóng trên ứng dụng."]),
            T("C", ["Vâng, cháu không sao đâu, phụ huynh yên tâm.", "Cảm ơn phụ huynh.", "Vâng, có gì phụ huynh xem thêm trong sổ liên lạc."]),
        ],
        "scam": [
            T("C", ["Cháu bị ngã chấn thương nặng, đang cấp cứu, phải đóng {amt} tạm ứng thì bệnh viện mới mổ.",
                    "Cháu đang nợ học phí, hôm nay không chuyển {amt} vào tài khoản của tôi thì cháu bị xóa tên.",
                    "Trường vừa đổi tài khoản thu, phụ huynh chuyển {amt} vào số tài khoản cá nhân tôi đọc ngay bây giờ."]),
            T("V", ["Để tôi chạy tới.", "Sao không thu qua ứng dụng?"] + HESITATE, 0.7),
            T("C", ["Không kịp đâu, phụ huynh chuyển trước đi, đừng gọi cho ai mất thời gian.",
                    "Ứng dụng đang lỗi, phụ huynh chuyển luôn kẻo hết hạn.",
                    "Từng phút đều quý, chuyển khoản ngay đi."]),
        ],
    },
    "bệnh viện báo người nhà": {
        "shared": [
            T("C", ["Alo, tôi gọi từ bệnh viện, {y} có phải người nhà của bệnh nhân vừa vào khoa không?",
                    "Bệnh viện đây ạ, người nhà của {y} đang được theo dõi ở khoa cấp cứu.",
                    "{M} là điều dưỡng, {m} gọi báo tình hình bệnh nhân cho gia đình."]),
            T("V", ["Dạ đúng, sao rồi ạ?", "Có nặng không?", "Tôi nghe đây."]),
        ],
        "legit": [
            T("C", ["Bệnh nhân đã ổn định, người nhà mang thẻ bảo hiểm y tế và căn cước lên làm thủ tục.",
                    "Bác sĩ cho theo dõi thêm một đêm, viện phí đóng tại quầy thu ngân tầng một khi ra viện.",
                    "Người nhà lên khoa gặp bác sĩ trực để nghe giải thích trực tiếp."]),
            T("V", ["Vâng tôi lên ngay.", "Có cần đóng tiền trước không?", "Nửa tiếng nữa tôi tới."]),
            T("C", ["Chưa cần, bệnh viện vẫn điều trị trước, thủ tục làm sau.", "Vâng, đi cẩn thận nhé.", "Vâng, khoa ở tầng ba."]),
        ],
        "scam": [
            T("C", ["Bệnh nhân nguy kịch, người nhà chuyển ngay {amt} vào tài khoản của bác sĩ thì mới mổ được.",
                    "Cần {amt} tiền máu và vật tư ngay bây giờ, chuyển khoản vào số tài khoản tôi đọc.",
                    "Phải có tiền trước mới làm thủ thuật, người nhà chuyển khoản luôn."]),
            T("V", ["Tôi tới liền.", "Bác sĩ cứ mổ đi, tôi đến ngay."], 0.7),
            T("C", ["Tới nơi thì trễ rồi, chuyển trước đi.", "Không còn thời gian gọi ai đâu, chuyển ngay.",
                    "Chậm một chút là không cứu được."]),
        ],
    },
    "xác minh hồ sơ vay": {
        "shared": [
            T("C", ["Chào {y}, {m} gọi từ {bank} về hồ sơ vay {y} đã đăng ký.",
                    "{M} là chuyên viên tín dụng, {m} gọi để trao đổi về khoản vay của {y}.",
                    "Dạ {m} bên công ty tài chính, hồ sơ vay của {y} đã có kết quả thẩm định."]),
            T("V", ["Kết quả sao em?", "Bao giờ giải ngân?", "Cần bổ sung gì không?"]),
        ],
        "legit": [
            T("C", ["Hồ sơ đạt, {y} mang căn cước ra chi nhánh ký hợp đồng, tiền giải ngân vào tài khoản sau khi ký.",
                    "{Y} cần bổ sung bảng lương ba tháng, nộp tại quầy hoặc gửi qua ứng dụng chính thức.",
                    "Lãi suất và phí đều ghi trong hợp đồng, {y} đọc kỹ tại quầy rồi mới ký."]),
            T("V", ["Có phải đóng phí trước không?", "Vâng mai {v} ra.", "Phí thế nào em?"]),
            T("C", ["Dạ không ạ, bên {m} không thu khoản nào trước khi giải ngân.", "Dạ {m} hẹn {y}.", "Dạ không có phí hồ sơ ạ."]),
        ],
        "scam": [
            T("C", ["Khoản vay bị treo vì sai số tài khoản, {y} nộp {small} để mở khóa hồ sơ.",
                    "{Y} chuyển trước phí bảo hiểm khoản vay mười phần trăm thì hệ thống mới giải ngân.",
                    "{Y} phải chuyển {amt} chứng minh tài chính, giải ngân xong sẽ hoàn lại."]),
            T("V", ["Trừ vào tiền vay không được sao?"] + HESITATE, 0.7),
            T("C", ["Không nộp thì hồ sơ bị hủy và {y} bị ghi nợ xấu.", "{Y} chuyển luôn nhé, {m} đang giữ suất.",
                    "Phải đóng trước mới ra tiền, {y} làm {deadline}."]),
        ],
    },
}
VALIDATION_PAIRS = {"nhà mạng báo thông tin thuê bao", "bưu phẩm chưa nhận"}

# --------------------------------------------------------- cặp ngắn: xin thông tin qua điện thoại (đợt 5c)
# Cuộc gọi ngắn, không dọa dẫm, không hối thúc: kẻ gọi chỉ tự giới thiệu rồi xin thông tin bí mật. Bản hợp pháp
# dùng cùng danh nghĩa và cùng danh từ (số thẻ, căn cước, mật khẩu, mã) nhưng mời ra quầy, bảo khách tự làm trên
# ứng dụng, hoặc nói rõ là không cần cung cấp. Mỗi lượt có bốn cách nói ghép được với nhau tùy ý.
SHORT_PAIRS = {
    "xin thông tin thẻ": {
        "shared": [
            T("C", ["{M} là nhân viên ngân hàng {bank}, {m} gọi về thẻ của {y}.",
                    "Chào {y}, {m} gọi từ trung tâm thẻ {bank}.",
                    "{M} bên {bank}, thẻ của {y} đang cần được kiểm tra lại.",
                    "Dạ {m} là giao dịch viên {bank}, {m} liên hệ về thẻ ghi nợ của {y}."]),
            T("V", ["Ừ, có việc gì?", "Thẻ {v} làm sao?", "{V} nghe đây.", "Vâng, nói đi."]),
        ],
        "legit": [
            T("C", ["Thẻ của {y} sắp hết hạn, {y} mang căn cước ra chi nhánh để nhận thẻ mới ạ.",
                    "{Y} tự kích hoạt thẻ trong ứng dụng ngân hàng là được, {m} không cần số thẻ của {y} đâu ạ.",
                    "Thẻ mới đã về phòng giao dịch, {y} ghé nhận trong giờ hành chính, {m} không hỏi số thẻ hay mật khẩu qua điện thoại.",
                    "{M} chỉ nhắc {y} đổi mã pin tại cây ATM, {y} đừng đọc số thẻ cho bất kỳ ai nhé."]),
            T("V", THANKS, 0.5),
        ],
        "scam": [
            T("C", ["{Y} đọc cho {m} dãy số in trên thẻ và ngày hết hạn để {m} kiểm tra.",
                    "{M} cần {y} xác nhận số thẻ, họ tên trên thẻ và ba số ở mặt sau.",
                    "{Y} cho {m} xin số thẻ với mã pin để {m} kích hoạt lại giúp {y}.",
                    "{Y} chụp hai mặt thẻ gửi qua {app} cho {m} để {m} cập nhật hồ sơ."]),
            T("V", HESITATE, 0.4),
        ],
    },
    "xin giấy tờ cho hồ sơ vay": {
        "shared": [
            T("C", ["{M} bên công ty tài chính, {m} gọi về hồ sơ vay của {y}.",
                    "Chào {y}, {m} là nhân viên tín dụng {bank}, hồ sơ vay của {y} đang được xử lý.",
                    "{M} gọi về khoản vay tiêu dùng {y} đăng ký.",
                    "Dạ {m} phụ trách hồ sơ vay của {y} ạ."]),
            T("V", ["Hồ sơ {v} sao rồi?", "Còn thiếu gì không?", "Ừ nói đi.", "Bao giờ có kết quả?"]),
        ],
        "legit": [
            T("C", ["Hồ sơ thiếu một bản photo căn cước, hôm nào ra văn phòng ký thì {y} cầm theo luôn ạ.",
                    "{Y} mang căn cước và sổ hộ khẩu ra chi nhánh, nhân viên sẽ đối chiếu bản gốc.",
                    "{Y} tự tải ảnh căn cước lên ứng dụng chính thức của công ty, {m} không nhận giấy tờ qua {app}.",
                    "Hồ sơ đủ rồi ạ, {y} chỉ cần ra văn phòng ký, {m} không cần {y} gửi thêm gì qua điện thoại."]),
            T("V", THANKS, 0.5),
        ],
        "scam": [
            T("C", ["{Y} chụp hai mặt căn cước gửi qua {app} cho {m} để {m} hoàn tất hồ sơ.",
                    "{Y} gửi ảnh chân dung cầm căn cước và ảnh thẻ ngân hàng vào số này để duyệt vay.",
                    "{Y} đọc số căn cước, số tài khoản và mật khẩu ngân hàng điện tử để {m} kiểm tra thu nhập.",
                    "{Y} nhắn cho {m} ảnh căn cước kèm số thẻ để {m} làm lệnh giải ngân."]),
            T("V", HESITATE, 0.4),
        ],
    },
    "xin thông tin tài khoản": {
        "shared": [
            T("C", ["Tôi gọi từ ngân hàng {bank}. Tài khoản của {y} đang có vấn đề.",
                    "{M} là nhân viên {bank}, tài khoản của {y} cần được rà soát.",
                    "Chào {y}, {m} bên {bank}, hệ thống báo tài khoản của {y} có sai lệch thông tin.",
                    "Ngân hàng {bank} xin thông báo tài khoản của {y} đang chờ xác minh."]),
            T("V", ["Vấn đề gì vậy?", "Sai lệch thế nào?", "Vậy phải làm sao?", "Ừ, {v} nghe."]),
        ],
        "legit": [
            T("C", ["{Y} ra quầy giao dịch mang theo căn cước, nhân viên sẽ cập nhật lại thông tin cho {y}.",
                    "{Y} tự cập nhật trong ứng dụng ngân hàng, {m} không cần {y} cung cấp số tài khoản hay mật khẩu.",
                    "{Y} gọi lại số tổng đài in trên thẻ để được hướng dẫn, {m} không xử lý qua cuộc gọi này.",
                    "Căn cước {y} đăng ký đã hết hạn, {y} mang căn cước mới ra chi nhánh để đổi ạ."]),
            T("V", THANKS, 0.5),
        ],
        "scam": [
            T("C", ["{Y} cho {m} số tài khoản và số dư hiện tại để {m} đối chiếu.",
                    "{Y} đọc tên đăng nhập và mật khẩu ngân hàng điện tử cho {m} kiểm tra.",
                    "{Y} cung cấp số tài khoản, số căn cước và mã vừa gửi về máy.",
                    "Cho {m} số tài khoản và mật khẩu giao dịch của {y} để {m} xử lý."]),
            T("V", HESITATE, 0.4),
        ],
    },
    "xin mã và mật khẩu ví điện tử": {
        "shared": [
            T("C", ["{M} là nhân viên chăm sóc khách hàng của ví điện tử, {m} gọi về tài khoản ví của {y}.",
                    "Chào {y}, {m} bên ví điện tử, ví của {y} vừa có yêu cầu hỗ trợ.",
                    "{M} gọi từ tổng đài ví điện tử về giao dịch gần đây của {y}.",
                    "Dạ {m} bên bộ phận hỗ trợ ví điện tử ạ."]),
            T("V", ["Ví {v} bị sao?", "Ừ, có gì không?", "{V} nghe.", "Giao dịch nào?"]),
        ],
        "legit": [
            T("C", ["Giao dịch của {y} đã thành công, {y} xem trong mục lịch sử của ứng dụng, {m} không cần mật khẩu của {y}.",
                    "{Y} tự đổi mật khẩu trong phần cài đặt của ứng dụng, đừng đọc mã xác thực cho ai kể cả {m}.",
                    "Tiền sẽ hoàn về ví trong hai mươi bốn giờ, {y} không phải cung cấp gì thêm.",
                    "{Y} liên kết lại ngân hàng ngay trong ứng dụng, {m} không hỏi mã pin hay mã OTP qua điện thoại."]),
            T("V", THANKS, 0.5),
        ],
        "scam": [
            T("C", ["{Y} cho {m} xin mật khẩu ví và mã xác thực vừa gửi về máy.",
                    "{Y} đọc mã pin của ví để {m} mở khóa giúp {y}.",
                    "{Y} đọc lại mã sáu số trong tin nhắn cho {m} để xác nhận chủ ví.",
                    "{Y} nhắn mật khẩu ví và số thẻ liên kết qua {app} cho {m}."]),
            T("V", HESITATE, 0.4),
        ],
    },
    "xin giấy tờ chuẩn hóa thuê bao": {
        "shared": [
            T("C", ["{M} là nhân viên {telco}, {m} gọi về thông tin thuê bao của {y}.",
                    "Chào {y}, tổng đài {telco} gọi về việc đăng ký sim của {y}.",
                    "{M} bên {telco}, sim của {y} cần bổ sung giấy tờ.",
                    "Dạ {m} gọi từ {telco} về gói cước và thông tin chính chủ của {y}."]),
            T("V", ["Bổ sung gì em?", "Ừ nói đi.", "Sim {v} làm sao?", "{V} đăng ký rồi mà."]),
        ],
        "legit": [
            T("C", ["{Y} mang căn cước ra cửa hàng {telco}, nhân viên chụp ảnh tại quầy cho {y}.",
                    "{Y} tự chụp căn cước trong ứng dụng của {telco}, {m} không nhận ảnh giấy tờ qua {app}.",
                    "Thông tin của {y} đã đủ rồi ạ, {m} chỉ gọi xác nhận, {y} không cần gửi gì.",
                    "{Y} ra điểm giao dịch lúc nào tiện, {m} không lấy mã xác nhận qua điện thoại đâu ạ."]),
            T("V", THANKS, 0.5),
        ],
        "scam": [
            T("C", ["{Y} gửi ảnh hai mặt căn cước qua {app} và đọc mã vừa về máy cho {m}.",
                    "{Y} đọc số căn cước, ngày cấp và mã xác nhận trong tin nhắn để {m} cập nhật từ xa.",
                    "{Y} chụp căn cước và ảnh khuôn mặt gửi vào số này cho {m}.",
                    "{Y} cho {m} xin mã {telco} vừa gửi về máy để {m} làm giúp."]),
            T("V", HESITATE, 0.4),
        ],
    },
}
VALIDATION_SHORT_PAIRS = {"xin giấy tờ chuẩn hóa thuê bao"}
PAIRS.update(SHORT_PAIRS)
VALIDATION_PAIRS.update(VALIDATION_SHORT_PAIRS)

for _name, _pair in PAIRS.items():
    # Cặp ngắn chỉ dùng bản lừa đảo. Đợt 5c dùng cả bản hợp pháp ngắn và model lệch hẳn về "bình thường" (sót Case D,
    # sót 6/16 cuộc gọi thật): một cuộc ba lượt mở đầu giống hệt lừa đảo thì gần như không còn gì để phân biệt.
    if _name not in SHORT_PAIRS:
        NORMAL[f"{_name} (hợp pháp)"] = _pair["shared"] + _pair["legit"]
    SCAM[f"{_name} (lừa đảo)"] = _pair["shared"] + _pair["scam"]
    if _name in VALIDATION_PAIRS:
        VALIDATION_FAMILIES.update({f"{_name} (lừa đảo)"} | ({f"{_name} (hợp pháp)"} - {f"{n} (hợp pháp)" for n in SHORT_PAIRS}))

# Cuộc gọi bình thường có chứa từ ngữ của lừa đảo: kể lại, cảnh báo, dặn dò. Từ khóa có mặt nhưng không ai bị ép gì.
NORMAL.update({
    "kể chuyện bị gọi lừa đảo": [
        T("C", ["Hôm qua có đứa gọi tao xưng công an, bảo tao liên quan vụ {crime}, đòi chuyển tiền vào tài khoản tạm giữ.",
                "Mẹ ơi nãy có người gọi con xưng ngân hàng, đòi con đọc mã OTP.",
                "Chị ơi em vừa nhận cuộc gọi báo trúng thưởng, bắt đóng phí hồ sơ trước."]),
        T("V", ["Rồi mày có chuyển không?", "Con có đọc không?", "Em có đóng không?"]),
        T("C", ["Không, tao biết lừa đảo nên cúp máy luôn.", "Dạ không, con tắt máy rồi chặn số luôn.", "Không chị, em biết là lừa đảo."]),
        T("V", ["Ừ, công an không ai làm việc qua điện thoại đâu.", "Giỏi, nhớ đừng đọc mã OTP cho ai nhé con.",
                "Ừ, trúng thưởng thật không ai bắt đóng tiền trước."]),
        T("C", ["Ừ, tao kể để mày cảnh giác.", "Dạ con biết rồi mẹ.", "Dạ em kể để chị dặn mọi người."], 0.8),
    ],
    "dặn người nhà cảnh giác": [
        T("C", ["Bố ơi dạo này lừa đảo nhiều lắm, ai gọi xưng công an hay ngân hàng đòi chuyển tiền thì bố cúp máy nhé.",
                "Mẹ nhớ không đọc mã OTP cho bất kỳ ai, kể cả người xưng là nhân viên ngân hàng.",
                "Bà ơi ai gọi bảo cháu bị tai nạn đòi chuyển tiền thì bà gọi lại cho cháu trước nhé."]),
        T("V", ["Ừ bố biết rồi.", "Mẹ nhớ rồi con.", "Ừ bà nhớ."]),
        T("C", ["Họ còn bắt cài ứng dụng lạ nữa, bố đừng cài gì hết.", "Có gì lạ mẹ gọi con hỏi trước đã.",
                "Họ hay hối thúc lắm, bà cứ bình tĩnh."]),
        T("V", ["Ừ, có gì bố gọi con.", "Ừ mẹ sẽ gọi con.", "Ừ bà biết rồi, cháu yên tâm."]),
    ],
    "ngân hàng thật cảnh báo lừa đảo": [
        T("C", ["Chào {y}, {m} gọi từ {bank} để thông báo ngân hàng đang có chương trình cảnh báo lừa đảo cho khách hàng.",
                "{M} bên {bank}, gần đây có đối tượng giả danh ngân hàng gọi điện, {m} gọi để nhắc {y} cảnh giác.",
                "Dạ {m} là nhân viên {bank}, {m} xin phép nhắc {y} vài lưu ý an toàn tài khoản."]),
        T("V", ["Ừ em nói đi.", "Vậy à.", "Lưu ý gì em?"]),
        T("C", ["Ngân hàng không bao giờ yêu cầu {y} đọc mã OTP, mật khẩu hay chuyển tiền sang tài khoản an toàn.",
                "{Y} không bấm vào đường link lạ và không cài ứng dụng theo yêu cầu của người gọi.",
                "Nếu có ai hối thúc chuyển tiền hoặc dọa khóa tài khoản, {y} cúp máy và gọi tổng đài in trên thẻ."]),
        T("V", THANKS),
    ],
})


def _capitalize(text: str) -> str:
    """Viết hoa chữ cái đầu của chuỗi."""
    return text[:1].upper() + text[1:]


def _fill(template: str, values: dict[str, str]) -> str:
    """Thay ``{bank}`` bằng giá trị, ``{Bank}`` bằng giá trị viết hoa chữ đầu, rồi viết hoa đầu câu."""
    for key, value in values.items():
        template = template.replace("{" + key.capitalize() + "}", _capitalize(value)).replace("{" + key + "}", value)
    return _capitalize(template)


def generate() -> list[dict]:
    """Sinh ``PER_FAMILY`` hội thoại cho mỗi kịch bản, không trùng nhau trong cùng kịch bản."""
    rng = random.Random(SEED)
    generic = set(DOUBT + ASK + HESITATE + AGREE + THANKS)
    rows = []
    for label, families in ((1, SCAM), (0, NORMAL)):
        for family, script in families.items():
            seen: set[str] = set()
            attempts = 0
            while len(seen) < PER_FAMILY and attempts < PER_FAMILY * 50:
                attempts += 1
                me, you, victim = rng.choice(PRONOUNS)
                values = {key: rng.choice(options) for key, options in FILLERS.items()}
                values |= {"m": me, "y": you, "v": victim}
                style = rng.choice(SPEAKER_STYLES)
                names = {"C": style[0], "V": style[1], "C2": style[2]}
                # Mỗi kịch bản có ba mạch chuyện: cách nói thứ k của các lượt lời thuộc cùng một mạch. Cuộc bình
                # thường luôn đi theo một mạch để câu hỏi và câu trả lời khớp nhau; cuộc lừa đảo thì một nửa số lần
                # trộn các mạch, vì các bước của kẻ lừa đảo (cái cớ, yêu cầu, hối thúc) thay thế được cho nhau.
                thread = rng.randrange(3)
                follow_thread = label == 0 or rng.random() < 0.5
                turns = []
                for speaker, options, keep in script:
                    if rng.random() >= keep:
                        continue
                    shared_pool = any(option in generic for option in options)
                    if follow_thread and not shared_pool and len(options) in (2, 3):
                        chosen = options[thread % len(options)]
                    else:
                        chosen = rng.choice(options)
                    turns.append([names[speaker], _fill(chosen, values)])
                key = " ".join(text for _, text in turns)
                if key in seen:
                    continue
                seen.add(key)
                rows.append({
                    "id": f"gen-{len(rows):04}", "label": label, "family": family, "turns": turns,
                    "split": "validation" if family in VALIDATION_FAMILIES else "train",
                })
    return rows


def main() -> int:
    """Sinh toàn bộ hội thoại theo kịch bản và ghi ra ``data/synthetic/vi_generated.jsonl``."""
    rows = generate()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8"))
    scams = sum(row["label"] for row in rows)
    print(f"wrote {OUT}: {len(rows)} conversations ({scams} scam, {len(rows) - scams} normal), "
          f"{len(SCAM)} scam families, {len(NORMAL)} normal families, "
          f"{sum(1 for row in rows if row['split'] == 'validation')} reserved for validation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
