"""Sinh các đoạn ngắn một người nói cho huấn luyện (đợt 7): chỉ có lời người gọi, không có người nghe đáp lại.

Cách dùng (chạy từ thư mục ``ai``):

    python -m tools.dataset_synthesize_vi_short

Vì sao cần: tới đợt 6, mọi đoạn ngắn một chiều có nhắc tới tiền trong dữ liệu huấn luyện đều là lừa đảo (chúng được
thêm ở đợt 5b để bắt các câu như "anh đọc mã OTP cho em"). Model vì thế học thành "người lạ gọi + nhờ thanh toán +
ngắn = lừa đảo" và báo mức cao cho khách sạn nhờ đặt cọc, cửa hàng nhờ giữ hàng... khi người dùng chỉ ghi được lời
người gọi. Bộ này thêm hai nửa đối xứng:

* ``NORMAL``: lời nhờ thanh toán, nhắc phí, mượn tiền trong đời thường. Điểm chung: việc đã có từ trước và người nghe
  biết (đã đặt phòng, đang học, đang thuê), có nhiều cách trả, không ép thời hạn tính bằng phút, không đòi mã hay
  thông tin thẻ, không cấm nói với ai.
* ``SCAM``: lời lừa đảo cùng chủ đề và cùng độ dài, để model không học ngược thành "ngắn + nhờ thanh toán = bình
  thường".

Kết quả ghi vào ``data/synthetic/vi_generated_short.jsonl``, cùng định dạng với ``vi_generated.jsonl`` nhưng mỗi dòng
chỉ có một lượt lời và có ``"monologue": true``; ``tools.dataset_prepare`` đọc file này và không cắt đoạn ngắn từ nó.
Khoảng một phần ba số dòng được viết thường, bỏ dấu câu, giống transcript mà Whisper trả về.

Mọi dòng là dữ liệu tổng hợp (``synthetic = true``). Bộ test cùng chủ đề (``tools/short_monologues_build.py``) viết
tay bằng câu chữ khác và có những loại hình không có ở đây (tiệc cưới, áo cưới, studio ảnh, showroom xe, nha khoa,
tiệm hoa, quỹ lớp, vật liệu xây dựng, nhà sách, phòng tập).
"""

import json
import random
import re
import sys
from pathlib import Path

OUT = Path("data/synthetic/vi_generated_short.jsonl")
SEED = 20261012
# Đợt 7 dùng 30 và 24 (python -m tools.dataset_synthesize_vi_short 30 24); đợt 7b dùng 10 và 10.
NORMAL_PER_FAMILY = 10
SCAM_PER_FAMILY = 10
# Tỉ lệ dòng viết theo kiểu transcript nhận dạng giọng nói: chữ thường, không dấu câu.
STT_STYLE_SHARE = 0.35

# (người gọi tự xưng, cách gọi người nghe)
PRONOUNS = [("em", "anh"), ("em", "chị"), ("cháu", "cô"), ("cháu", "bác"), ("em", "anh chị"), ("tôi", "anh"),
            ("tôi", "chị")]
SLOTS = {
    "small": ["hai trăm nghìn", "ba trăm nghìn", "năm trăm nghìn", "bảy trăm nghìn", "một triệu", "một triệu rưỡi"],
    "amt": ["hai triệu", "ba triệu rưỡi", "năm triệu", "tám triệu", "mười hai triệu", "hai mươi triệu"],
    "big": ["ba mươi triệu", "năm mươi triệu", "tám mươi triệu", "một trăm hai mươi triệu"],
    "day": ["thứ hai", "thứ tư", "thứ sáu", "chủ nhật", "ngày mười lăm", "ngày hai mươi", "cuối tháng"],
    "city": ["Đà Nẵng", "Nha Trang", "Sa Pa", "Huế", "Vũng Tàu", "Hạ Long", "Quy Nhơn"],
    "item": ["cái máy giặt", "bộ bàn ghế", "cái điện thoại", "cái tivi", "chiếc xe đạp điện", "cái máy lọc không khí"],
    "bank": ["Vietcombank", "Techcombank", "BIDV", "Agribank", "MB", "ACB", "VPBank"],
    "soon": ["trong ba mươi phút nữa", "ngay bây giờ", "trong vòng một tiếng", "trước mười hai giờ trưa nay",
             "trong hôm nay"],
}

# Mỗi kịch bản là ba phần nối lại: mở đầu, nội dung chính, kết. Mỗi phần có vài cách nói.
NORMAL = {
    "khách sạn nhờ đặt cọc": [
        ["Chào {y}, {m} gọi từ khách sạn ở {city}.", "Dạ {m} bên lễ tân khách sạn ạ.",
         "{M} gọi xác nhận đặt phòng của {y} ở {city} ạ."],
        ["Phòng {y} đặt cho {day} bên {m} đang giữ, {y} chuyển khoản cọc {small} để chốt phòng giúp {m}.",
         "Để giữ phòng dịp cao điểm bên {m} nhận cọc trước {small}, {y} chuyển khoản hoặc cọc bằng thẻ khi tới cũng được.",
         "{Y} đặt hai phòng {day}, bên {m} xin cọc {small}, số tài khoản có trong thư xác nhận đặt phòng."],
        ["Khi nào tiện {y} chuyển rồi báo {m} nhé.", "{Y} cần đổi ngày thì cứ gọi lại số lễ tân này ạ.",
         "Nếu {y} hủy trước ba ngày bên {m} hoàn cọc đầy đủ.", "{M} cảm ơn {y}, hẹn gặp {y} {day}."],
    ],
    "cửa hàng nhờ đặt cọc giữ hàng": [
        ["Chào {y}, {m} ở cửa hàng hôm trước {y} ghé xem {item}.", "{M} gọi từ cửa hàng, {item} {y} hỏi đã có hàng.",
         "Dạ {m} bên cửa hàng đây, {y} còn lấy {item} không ạ?"],
        ["Mẫu đó còn một cái, {y} muốn giữ thì đặt cọc {small}, phần còn lại trả khi nhận hàng.",
         "{Y} ghé cửa hàng cọc {small} hoặc chuyển khoản theo số trên hóa đơn báo giá, bên {m} giữ đến {day}.",
         "Đang có khách khác hỏi, {y} cọc trước {small} thì {m} để riêng ra cho {y}."],
        ["{Y} cứ suy nghĩ rồi báo lại {m} cũng được.", "Bên {m} có viết phiếu thu cho {y} đàng hoàng.",
         "Không lấy nữa {y} nhắn {m} một tiếng để {m} bán cho khách khác nhé."],
    ],
    "nhà xe, vé nhờ thanh toán": [
        ["Alo {y}, {m} bên phòng vé nhà xe.", "Chào {y}, {m} gọi về vé đi {city} của {y}.",
         "{M} ở đại lý vé, chỗ {y} đặt đi {city} {m} đang giữ."],
        ["Xe chạy {day}, {y} thanh toán trước {small} tiền vé để {m} xuất vé, hoặc ra quầy lấy vé trước giờ chạy một tiếng.",
         "{Y} chuyển khoản tiền vé {small} theo số tài khoản của nhà xe ghi trên tin nhắn đặt chỗ nhé.",
         "Vé giữ được đến tối nay, {y} trả tiền ở quầy hay chuyển khoản đều được."],
        ["Có gì thay đổi {y} báo {m} trước nhé.", "{M} cảm ơn {y}.", "Lên xe {y} đọc số điện thoại là được ạ."],
    ],
    "trường nhắc học phí": [
        ["Chào phụ huynh, {m} là giáo viên chủ nhiệm của cháu.", "Dạ {m} ở phòng tài vụ của trường ạ.",
         "{M} gọi từ văn phòng trường, {m} xin phép nhắc gia đình một việc."],
        ["Học phí tháng này của cháu là {small}, hạn nộp là {day}, gia đình đóng ở phòng tài vụ hoặc chuyển khoản theo thông báo của trường.",
         "Nhà trường thu học phí học kỳ mới đến hết {day}, số tiền ghi trong giấy báo cháu mang về.",
         "Cháu còn thiếu khoản tiền ăn bán trú {small}, {y} gửi cháu mang đi hoặc nộp qua ứng dụng của trường nhé."],
        ["Gia đình có khó khăn gì cứ trao đổi với {m}.", "{M} cảm ơn {y} nhiều ạ.",
         "Nếu {y} đã nộp rồi thì bỏ qua lời nhắc này giúp {m}."],
    ],
    "bảo hiểm nhắc đóng phí": [
        ["Chào {y}, {m} là tư vấn viên phụ trách hợp đồng bảo hiểm của {y}.", "{M} gọi từ công ty bảo hiểm ạ.",
         "Dạ {m} bên bảo hiểm nhân thọ, {m} gọi nhắc {y} kỳ phí."],
        ["Hợp đồng của {y} đến hạn đóng phí vào {day}, số tiền vẫn là {amt} như năm trước.",
         "Kỳ phí năm nay của {y} là {amt}, {y} đóng trên ứng dụng của công ty hoặc tại văn phòng đều được.",
         "{Y} còn ba mươi ngày gia hạn đóng phí, {y} thu xếp trước {day} để quyền lợi không gián đoạn."],
        ["{Y} cần {m} gửi lại thông báo phí thì nói {m} nhé.", "{M} không thu tiền mặt, {y} đóng thẳng cho công ty ạ.",
         "Có gì chưa rõ {y} gọi tổng đài in trên hợp đồng."],
    ],
    "điện nước internet nhắc cước": [
        ["Chào {y}, {m} gọi từ tổng đài chăm sóc khách hàng.", "{M} bên nhà mạng internet ạ.",
         "Dạ {m} ở công ty cấp nước, {m} gọi về hóa đơn tháng này."],
        ["Hóa đơn tháng này của nhà mình là {small}, hạn thanh toán là {day}.",
         "Cước tháng trước {small} chưa được thanh toán, {y} trả qua ứng dụng ngân hàng hoặc ở cửa hàng tiện lợi giúp {m}.",
         "Nhà mình còn một kỳ hóa đơn {small}, {y} thanh toán trước {day} để không bị tạm ngưng dịch vụ."],
        ["{Y} đã trả rồi thì hệ thống sẽ tự cập nhật ạ.", "{M} cảm ơn {y}.",
         "{Y} xem chi tiết hóa đơn trong ứng dụng của công ty nhé."],
    ],
    "chủ nhà nhắc tiền thuê": [
        ["{Y} ơi {m} chủ nhà đây.", "Alo {y}, {m} gọi về tiền phòng tháng này.", "Chào {y}, {m} bên cho thuê nhà."],
        ["Tháng này tiền nhà {amt}, điện nước {small}, {y} chuyển khoản cho {m} như mọi tháng nhé.",
         "Đến kỳ đóng tiền trọ rồi, {y} gửi {m} trước {day} giúp {m}.",
         "Tiền điện tháng này tăng một chút, tổng cộng {amt}, {m} gửi ảnh công tơ qua tin nhắn rồi."],
        ["{Y} kẹt thì báo {m} chậm vài hôm cũng được.", "Cảm ơn {y} nhé.", "Có gì hỏng hóc trong phòng {y} báo {m} sửa."],
    ],
    "ban quản lý nhắc phí": [
        ["Chào {y}, {m} ở ban quản lý tòa nhà.", "Dạ {m} bên văn phòng ban quản lý chung cư ạ.",
         "{M} gọi từ ban quản lý, căn hộ nhà mình có một khoản chưa đóng."],
        ["Phí gửi xe quý này là {small}, {y} đóng tại quầy lễ tân trước {day}.",
         "Phí dịch vụ tháng này {small}, {y} chuyển khoản theo thông báo gửi trong hộp thư hoặc đóng ở văn phòng.",
         "Thẻ thang máy của nhà mình sắp hết hạn, {y} xuống văn phòng gia hạn, phí là {small}."],
        ["Văn phòng mở cửa giờ hành chính ạ.", "{M} cảm ơn {y}.", "{Y} đóng rồi thì giữ biên lai giúp {m}."],
    ],
    "bạn bè mượn tiền": [
        ["Ê mày ơi tao đây.", "Alo ông ơi, tôi nè.", "Bà ơi tui đây, rảnh nói chuyện tí không."],
        ["Tao đang kẹt tiền nhà, mày cho tao mượn {amt} được không, cuối tháng lĩnh lương tao trả.",
         "Tôi cần {amt} đóng viện phí cho mẹ, ông có thì cho tôi vay, đầu tháng tôi gửi lại.",
         "Tui thiếu {small} nữa mới đủ tiền học cho con, bà cho tui mượn đỡ, tuần sau tui trả."],
        ["Mày chuyển vào tài khoản của tao như lần trước nha.", "Không tiện thì thôi, đừng ngại nha.",
         "Tối tao qua nhà mày lấy cũng được.", "Cảm ơn nhiều, có gì tôi mời cà phê."],
    ],
    "con cái xin tiền bố mẹ": [
        ["Mẹ ơi con đây.", "Bố ơi con nè.", "Mẹ à, con gọi nhờ mẹ chút việc."],
        ["Tháng này con đóng tiền phòng với mua sách hết nhiều, mẹ gửi thêm cho con {small} được không.",
         "Trường con thu tiền thực tập {amt}, bố chuyển cho con vào tài khoản của con nhé.",
         "Con định đăng ký lớp tiếng Anh, học phí {amt}, bố mẹ cho con xin."],
        ["Cuối tuần con về con kể mẹ nghe.", "Con vẫn khỏe, bố mẹ đừng lo.", "Khi nào tiện mẹ chuyển cũng được ạ."],
    ],
    "chia tiền ăn uống": [
        ["Mọi người ơi, tôi báo tiền liên hoan hôm qua.", "Ê, tối qua đi ăn tổng hết {amt}.",
         "Chị ơi em tính xong tiền du lịch nhóm rồi."],
        ["Chia đều mỗi người {small}, ai tiện thì chuyển khoản cho tôi, tôi ứng trước rồi.",
         "Phần của mày là {small}, mày gửi tao lúc nào cũng được.",
         "Mỗi nhà đóng {small}, chị chuyển vào tài khoản em hoặc mai lên công ty đưa em."],
        ["Tôi gửi hóa đơn lên nhóm rồi đó.", "Không gấp đâu nha.", "Thiếu thừa gì tao tính lại sau."],
    ],
    "giao hàng thu hộ": [
        ["Alo {y} ơi {m} giao hàng đây.", "{Y} ơi {m} shipper, {y} có đơn hàng.", "Chào {y}, {m} giao đơn cho {y} đây ạ."],
        ["Đơn của {y} thu hộ {small}, {m} đang ở dưới cổng, {y} xuống nhận giúp {m}.",
         "Hàng thu hộ {small}, {y} trả tiền mặt hay quét mã chuyển khoản cho {m} đều được.",
         "{Y} không có nhà thì {m} gửi hàng xóm, tiền thu hộ {small} {y} chuyển khoản theo mã trên đơn."],
        ["{M} chờ được năm phút thôi ạ.", "{Y} kiểm hàng rồi hãy trả tiền nhé.", "Không nhận được thì {m} hẹn giao lại {day}."],
    ],
    "thợ sửa chữa báo giá": [
        ["{Y} ơi {m} thợ sửa hôm qua qua nhà mình.", "Chào {y}, {m} ở tiệm sửa chữa.",
         "Alo {y}, máy của {y} {m} kiểm tra xong rồi."],
        ["Phải thay linh kiện, tổng hết {small}, {y} đồng ý thì {m} làm luôn.",
         "Tiền công với vật tư là {small}, {y} trả khi {m} lắp xong hoặc chuyển khoản cũng được.",
         "Sửa xong rồi, hết {small}, {y} qua lấy và thanh toán tại tiệm nhé."],
        ["Bên {m} bảo hành ba tháng.", "{Y} không sửa nữa cũng không sao, {m} không tính phí kiểm tra.",
         "{Y} cần hóa đơn thì {m} viết cho."],
    ],
    "phòng khám báo chi phí": [
        ["Chào {y}, phòng khám gọi xác nhận lịch hẹn.", "Dạ {m} ở quầy tiếp đón phòng khám ạ.",
         "{M} gọi từ bệnh viện, lịch khám của {y} là {day}."],
        ["Gói khám {y} chọn có giá {amt}, {y} thanh toán tại quầy khi đến khám.",
         "{Y} nhớ mang thẻ bảo hiểm y tế, phần chênh lệch khoảng {small} đóng tại quầy thu ngân.",
         "Kết quả xét nghiệm có rồi, {y} qua lấy và đóng nốt {small} còn thiếu nhé."],
        ["{Y} đến sớm mười lăm phút giúp {m}.", "Cần đổi lịch {y} gọi lại số này.", "{M} cảm ơn {y}."],
    ],
    "spa, làm đẹp nhắc lịch": [
        ["Chào {y}, {m} ở tiệm tóc.", "Dạ {m} bên spa, {m} gọi nhắc lịch hẹn của {y}.", "{Y} ơi {m} ở tiệm nail đây."],
        ["Liệu trình của {y} còn hai buổi, buổi tới là {day}, phần còn lại {small} {y} thanh toán tại quầy.",
         "Bên {m} có ưu đãi gia hạn thẻ thành viên {small}, {y} thích thì hôm tới làm {m} tư vấn thêm.",
         "{Y} đặt lịch {day} rồi nhé, tổng dịch vụ khoảng {small}, {y} trả sau khi làm xong."],
        ["{Y} bận thì báo {m} dời lịch.", "Hẹn gặp {y} ạ.", "{M} cảm ơn {y}."],
    ],
    "công ty du lịch nhắc thanh toán": [
        ["Chào {y}, {m} bên công ty du lịch.", "{M} gọi về tour đi {city} của gia đình {y}.",
         "Dạ {m} là điều hành tour, {m} báo {y} lịch thanh toán."],
        ["Tour khởi hành {day}, {y} thanh toán nốt {amt} tại văn phòng hoặc chuyển vào tài khoản công ty ghi trên hợp đồng.",
         "Bên {m} đã đặt xong vé và phòng, phần còn lại là {amt}, hạn thanh toán trước ngày đi năm ngày.",
         "{Y} đã cọc rồi, còn {amt} {y} đóng khi nhận lịch trình chi tiết cũng được."],
        ["{M} gửi hóa đơn qua thư điện tử cho {y}.", "Có thay đổi số người {y} báo {m} sớm.", "{M} cảm ơn {y}."],
    ],
    "người bán hàng chốt đơn": [
        ["Chào {y}, {m} ở shop {y} đặt hàng hôm qua.", "{M} gọi xác nhận đơn hàng của {y}.",
         "Dạ {m} bên cửa hàng trên mạng, {y} đặt {item} đúng không ạ?"],
        ["Đơn của {y} tổng {small}, {y} muốn trả khi nhận hàng hay chuyển khoản trước để được miễn phí giao?",
         "Hàng có sẵn, {m} gửi {day}, {y} nhận hàng kiểm tra rồi thanh toán {small} cho bên giao hàng.",
         "{Y} chuyển khoản {small} theo thông tin trên trang của shop thì {m} gửi hàng trong hôm nay."],
        ["{Y} muốn đổi mẫu thì nhắn {m} trước khi gửi.", "{M} cảm ơn {y} đã ủng hộ.", "Hàng lỗi bên {m} đổi trong bảy ngày."],
    ],
    "ngân hàng thật nhắc kỳ trả góp": [
        ["Chào {y}, {m} gọi từ {bank} theo lịch nhắc nợ.", "{M} là nhân viên {bank}, {m} nhắc {y} kỳ thanh toán.",
         "Dạ {bank} xin nhắc {y} khoản trả góp tháng này."],
        ["Kỳ này {y} cần thanh toán {amt} trước {day}, {y} nộp vào chính tài khoản của {y} trên ứng dụng như mọi kỳ.",
         "Dư nợ thẻ đến hạn {day} là {amt}, {y} trả tại quầy, cây ATM hoặc ứng dụng ngân hàng đều được.",
         "{Y} để đủ {amt} trong tài khoản trước {day}, hệ thống sẽ tự trích nợ."],
        ["{M} không hỏi mật khẩu hay mã OTP của {y} qua điện thoại.", "Có thắc mắc {y} gọi tổng đài in sau thẻ.",
         "{Y} đã thanh toán rồi thì bỏ qua cuộc gọi này ạ."],
    ],
    "trung tâm học nhắc gia hạn": [
        ["Chào {y}, {m} ở trung tâm ngoại ngữ.", "Dạ {m} bên lớp năng khiếu của bé ạ.",
         "{M} gọi từ trung tâm dạy lái xe, {m} báo {y} lịch học."],
        ["Khóa hiện tại kết thúc {day}, {y} học tiếp thì đóng học phí khóa mới {amt} tại quầy.",
         "Học phí đợt hai là {amt}, {y} đóng trước buổi học {day} giúp trung tâm.",
         "Bên {m} đang giảm mười phần trăm cho học viên cũ đăng ký trước {day}, {y} cân nhắc nhé."],
        ["{Y} cần bảo lưu thì nói {m}.", "{M} cảm ơn {y}.", "Chi tiết {m} gửi qua tin nhắn cho {y}."],
    ],
    "hội nhóm, họ hàng góp tiền": [
        ["Anh ơi em là thủ quỹ câu lạc bộ.", "Cô ơi cháu gọi thay mẹ cháu.", "Chú ơi cháu là lớp trưởng họp lớp năm nay."],
        ["Quỹ năm nay mỗi người {small}, anh chuyển khoản cho em hoặc đóng hôm sinh hoạt tới.",
         "Nhà mình góp giỗ ông bà mỗi nhà {small}, cô gửi mẹ cháu trước {day} là được.",
         "Họp lớp mỗi người đóng {small}, chú chuyển cho cháu hay hôm đó nộp cũng được."],
        ["Em có ghi sổ thu chi gửi lên nhóm.", "Không gấp đâu ạ.", "Cháu cảm ơn."],
    ],
    "giữ chỗ nhà hàng, sân bóng": [
        ["Chào {y}, {m} bên nhà hàng.", "{M} gọi từ sân bóng, {y} đặt sân tối {day}.", "Dạ {m} ở quán, {y} đặt bàn mười người đúng không ạ?"],
        ["Bàn đông người bên {m} xin cọc {small}, {y} chuyển khoản hoặc ghé quán cọc đều được.",
         "Sân giờ đẹp nên {m} nhận cọc {small}, trừ vào tiền sân hôm đá.",
         "{Y} đặt thực đơn trước thì cọc một nửa, khoảng {small}, {m} gửi thực đơn qua tin nhắn."],
        ["Hủy trước một ngày {m} hoàn cọc.", "{M} giữ bàn đến bảy giờ tối nhé.", "{M} cảm ơn {y}."],
    ],
    "thuê xe, thuê đồ": [
        ["Chào {y}, {m} bên cho thuê xe tự lái.", "{M} gọi từ tiệm cho thuê đồ cắm trại.", "Dạ {m} bên cho thuê xe máy ở {city} ạ."],
        ["Xe {y} thuê từ {day}, {y} đặt cọc {amt} khi nhận xe, trả xe bên {m} hoàn lại.",
         "Bộ đồ {y} đặt thuê hai ngày hết {small}, {y} trả khi đến lấy.",
         "{Y} giữ xe thì chuyển khoản trước {small}, mang căn cước khi nhận xe để làm hợp đồng."],
        ["{Y} xem xe kỹ rồi hãy ký nhé.", "Có hợp đồng thuê rõ ràng ạ.", "{M} cảm ơn {y}."],
    ],
}

SCAM = {
    "giả điện lực dọa cắt điện": [
        ["{M} gọi từ công ty điện lực.", "Đây là tổng đài điện lực thông báo khẩn.", "{M} là nhân viên điện lực khu vực."],
        ["Nhà {y} nợ tiền điện, {soon} không chuyển {small} vào số tài khoản {m} đọc thì bị cắt điện.",
         "Hợp đồng điện của {y} bị khóa vì nợ cước, {y} chuyển khoản ngay vào tài khoản cá nhân của nhân viên thu.",
         "{Y} cài ứng dụng theo đường link {m} gửi để thanh toán, không là cắt điện {soon}."],
        ["{Y} làm ngay kẻo mất điện cả nhà.", "{M} chỉ giữ lệnh được mười phút.", "{Y} đừng ra điểm thu, không kịp đâu."],
    ],
    "giả người nhà cấp cứu": [
        ["Anh chị là người nhà của bệnh nhân vừa nhập viện phải không.", "Tôi là bác sĩ khoa cấp cứu.",
         "Em là giáo viên của bé, bé vừa bị tai nạn ở trường."],
        ["Bệnh nhân cần mổ gấp, gia đình chuyển ngay {amt} tạm ứng vào tài khoản tôi đọc.",
         "Phải đóng viện phí {amt} {soon} mới làm thủ thuật được, anh chị chuyển khoản luôn.",
         "Bé đang nguy kịch, phụ huynh chuyển {big} vào tài khoản của bác sĩ rồi hãy lên viện."],
        ["Đừng tắt máy, chuyển xong đọc mã giao dịch cho tôi.", "Chậm là không cứu được đâu.",
         "Anh chị đừng gọi cho ai, làm ngay đi."],
    ],
    "giả bạn đổi số vay gấp": [
        ["Mày ơi tao đây, tao mới đổi số.", "Chị ơi em đây, điện thoại em hỏng nên em dùng số này.",
         "Ông ơi tôi nè, tôi đang dùng nhờ máy bạn."],
        ["Tao cần gấp {amt}, mày chuyển vào tài khoản người quen của tao, tên khác nhưng đúng đấy.",
         "Em đang kẹt ở sân bay, chị chuyển giúp em {amt} vào tài khoản này {soon}.",
         "Tôi cần {big} đáo hạn ngân hàng, ông chuyển vào số tài khoản tôi nhắn, mai tôi trả cả lãi."],
        ["Đừng gọi số cũ, tao không nghe được.", "Chuyển xong chụp màn hình gửi em ngay.", "Việc này đừng nói với vợ tôi."],
    ],
    "giả khách sạn, phòng vé đòi thẻ": [
        ["{M} gọi từ bộ phận đặt phòng.", "{M} là nhân viên phòng vé máy bay.", "Đây là trung tâm hỗ trợ đặt phòng trực tuyến."],
        ["Thanh toán của {y} bị lỗi, {y} đọc số thẻ, ngày hết hạn và ba số mặt sau để {m} giữ chỗ.",
         "Đặt chỗ của {y} sắp bị hủy, {y} bấm vào đường link {m} gửi và nhập thông tin thẻ {soon}.",
         "{Y} đọc mã OTP vừa gửi về máy để {m} xác nhận hoàn tiền đặt cọc."],
        ["{M} chỉ giữ được chỗ thêm mười phút.", "Không làm ngay {y} mất cả tiền phòng.", "{Y} đọc luôn đi, {m} đang chờ."],
    ],
    "giả giao hàng gửi link": [
        ["{M} là nhân viên giao hàng.", "{M} gọi từ kho vận chuyển.", "Alo {y}, {m} shipper đây."],
        ["Đơn của {y} bị kẹt ở kho, {y} bấm vào link {m} nhắn rồi nhập số tài khoản và mật khẩu để đóng phí lưu kho.",
         "{M} lỡ đăng ký nhầm {y} vào gói hội viên giao hàng, {y} đọc mã OTP để {m} hủy không là bị trừ tiền mỗi tháng.",
         "Hàng của {y} cần đóng thuế {small}, {y} chuyển vào tài khoản cá nhân của {m} {soon}."],
        ["Không làm là hàng bị hoàn và {y} bị phạt.", "{Y} làm ngay giúp {m}.", "Mã vừa gửi đó, {y} đọc cho {m}."],
    ],
    "giả bảo hiểm hoàn phí": [
        ["{M} gọi từ công ty bảo hiểm.", "{M} bên bảo hiểm xã hội.", "Đây là bộ phận hoàn phí bảo hiểm."],
        ["{Y} được hoàn {amt}, {y} đọc số tài khoản và mã xác nhận gửi về điện thoại để nhận tiền.",
         "Hồ sơ hoàn phí của {y} hết hạn hôm nay, {y} cài ứng dụng theo đường link {m} gửi rồi đăng nhập ngân hàng.",
         "Để nhận tiền hoàn {y} đóng trước {small} phí xử lý hồ sơ vào tài khoản {m} đọc."],
        ["Quá hạn là mất quyền lợi.", "{Y} đọc mã cho {m} luôn nhé.", "Chỉ còn hôm nay thôi ạ."],
    ],
    "vay tiền đóng phí trước": [
        ["{M} bên công ty tài chính.", "{M} gọi từ ứng dụng vay nhanh.", "Chúc mừng {y}, hồ sơ vay của {y} đã được duyệt."],
        ["Khoản vay {big} đã sẵn sàng, {y} chuyển {small} phí bảo hiểm khoản vay thì tiền về tài khoản ngay.",
         "{Y} nhập sai số tài khoản nên tiền bị đóng băng, {y} nộp {amt} để mở khóa giải ngân.",
         "Muốn giải ngân {soon} {y} đóng phí xác minh {small} vào tài khoản cá nhân của nhân viên thẩm định."],
        ["Đóng xong năm phút là có tiền.", "Không đóng thì hồ sơ bị hủy và {y} bị báo nợ xấu.", "{Y} chuyển ngay đi."],
    ],
    "trúng thưởng đóng phí": [
        ["Chúc mừng {y} đã trúng giải đặc biệt.", "{M} gọi từ chương trình tri ân khách hàng.", "Số điện thoại của {y} vừa trúng thưởng."],
        ["Để nhận quà {y} chuyển {small} tiền thuế và phí vận chuyển {soon}.",
         "{Y} đọc số thẻ ngân hàng và mã OTP để bên {m} chuyển tiền thưởng {big}.",
         "{Y} đóng {small} phí hồ sơ vào tài khoản {m} đọc, quà sẽ giao trong hôm nay."],
        ["Quá giờ giải thưởng chuyển cho người khác.", "{Y} giữ bí mật để tránh bị tranh giải.", "{Y} làm luôn nhé."],
    ],
    "việc làm nạp tiền nhiệm vụ": [
        ["{M} bên phòng nhân sự sàn thương mại điện tử.", "Chúc mừng {y} được nhận làm cộng tác viên.", "{M} là quản lý nhóm việc làm tại nhà."],
        ["{Y} nạp {small} làm nhiệm vụ đầu tiên, xong là rút cả gốc lẫn hoa hồng.",
         "Đơn tiếp theo cần ứng {amt}, {y} chuyển vào tài khoản kế toán {soon} để không bị khóa tài khoản.",
         "{Y} làm sai thao tác nên phải nạp thêm {amt} mới rút được tiền về."],
        ["Càng nạp nhiều hoa hồng càng cao.", "Không nạp là mất hết tiền đã làm.", "{Y} chuyển ngay để giữ suất."],
    ],
    "giả công an, tài khoản an toàn": [
        ["Tôi là cán bộ cơ quan điều tra.", "Đây là công an thành phố.", "Tôi gọi từ viện kiểm sát."],
        ["{Y} liên quan một vụ rửa tiền, {y} chuyển toàn bộ tiền sang tài khoản tạm giữ để xác minh.",
         "{Y} kê khai số dư các tài khoản rồi chuyển {big} vào tài khoản an toàn của cơ quan điều tra {soon}.",
         "{Y} cài ứng dụng theo hướng dẫn và không được cúp máy trong lúc làm việc."],
        ["Việc này là mật, {y} không được nói với người nhà.", "Không hợp tác {y} sẽ bị tạm giam.", "{Y} ra chỗ vắng người rồi làm."],
    ],
    "giả ngân hàng đòi mã": [
        ["{M} gọi từ ngân hàng {bank}.", "{M} là nhân viên chăm sóc khách hàng {bank}.", "Đây là trung tâm thẻ {bank}."],
        ["Tài khoản của {y} vừa bị trừ {amt}, {y} đọc mã OTP để {m} hủy giao dịch.",
         "Thẻ của {y} sắp bị khóa, {y} đọc số thẻ và mật khẩu ngân hàng điện tử để {m} mở lại.",
         "{Y} chuyển hết tiền sang tài khoản mới {m} vừa tạo để tránh bị trừ tiếp."],
        ["{Y} đọc ngay, mã chỉ có hiệu lực hai phút.", "Chậm là mất tiền đó {y}.", "{M} đang chờ máy."],
    ],
    "giả nhà mạng khóa thuê bao": [
        ["{M} gọi từ nhà mạng.", "Đây là tổng đài viễn thông.", "{M} là nhân viên kỹ thuật nhà mạng."],
        ["Thuê bao của {y} sẽ bị khóa hai chiều {soon}, {y} đọc mã vừa gửi về máy để chuẩn hóa thông tin.",
         "{Y} soạn tin theo cú pháp {m} đọc để nâng cấp sim, không là mất số.",
         "{Y} gửi ảnh hai mặt căn cước và đọc mã xác nhận cho {m}."],
        ["{Y} làm ngay kẻo mất số.", "{M} chỉ hỗ trợ được trong hôm nay.", "Mã đến rồi, {y} đọc đi."],
    ],
    "giả đối tác đổi số tài khoản": [
        ["{M} bên kế toán của nhà cung cấp.", "{M} gọi thay chủ nhà, chủ nhà đang đi nước ngoài.", "{M} là trợ lý giám đốc, sếp nhờ {m} gọi."],
        ["Tài khoản cũ đang bị kiểm tra, khoản {big} kỳ này {y} chuyển vào số tài khoản cá nhân {m} đọc.",
         "Tiền nhà từ tháng này {y} chuyển vào tài khoản mới, {y} chuyển luôn ba tháng {soon}.",
         "Sếp cần {big} ký hợp đồng gấp, {y} chuyển ngay vào tài khoản này rồi báo cáo sau."],
        ["{Y} đừng gọi lại số cũ, không liên lạc được đâu.", "Việc gấp, {y} chuyển trước rồi hỏi sau.", "Đừng nói với ai trong công ty."],
    ],
}

# Kịch bản để dành cho validation: model không được thấy chúng khi huấn luyện.
VALIDATION_FAMILIES = {"thuê xe, thuê đồ", "giữ chỗ nhà hàng, sân bóng", "trung tâm học nhắc gia hạn",
                       "giả đối tác đổi số tài khoản", "giả nhà mạng khóa thuê bao"}

_PUNCTUATION = re.compile(r"[.,!?;:]")


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]


def _fill(template: str, values: dict[str, str]) -> str:
    """Thay ``{y}`` bằng giá trị, ``{Y}`` bằng giá trị viết hoa chữ đầu, rồi viết hoa đầu câu."""
    for key, value in values.items():
        template = template.replace("{" + key.upper() + "}", _capitalize(value)) \
            .replace("{" + key.capitalize() + "}", _capitalize(value)).replace("{" + key + "}", value)
    return _capitalize(template)


def _like_transcript(text: str) -> str:
    """Viết lại như transcript nhận dạng giọng nói: chữ thường, không dấu câu."""
    return " ".join(_PUNCTUATION.sub(" ", text).lower().split())


def generate(normal_per_family: int = NORMAL_PER_FAMILY, scam_per_family: int = SCAM_PER_FAMILY) -> list[dict]:
    """Sinh mọi đoạn; mỗi kịch bản cho ra các tổ hợp khác nhau của mở đầu, nội dung, kết, xưng hô và chi tiết."""
    rng = random.Random(SEED)
    rows = []
    for label, families, per_family in ((0, NORMAL, normal_per_family), (1, SCAM, scam_per_family)):
        for family, (openings, bodies, closings) in families.items():
            seen: set[str] = set()
            attempts = 0
            while len(seen) < per_family and attempts < per_family * 50:
                attempts += 1
                caller, listener = rng.choice(PRONOUNS)
                values = {"m": caller, "y": listener, **{key: rng.choice(options) for key, options in SLOTS.items()}}
                parts = [rng.choice(openings), rng.choice(bodies)]
                # Một phần tư số đoạn không có câu kết, một phần nhỏ không có câu mở đầu: người dùng bấm ghi không
                # đúng lúc bắt đầu cuộc gọi.
                if rng.random() < 0.75:
                    parts.append(rng.choice(closings))
                if rng.random() < 0.15:
                    parts = parts[1:]
                text = " ".join(_fill(part, values) for part in parts)
                if rng.random() < STT_STYLE_SHARE:
                    text = _like_transcript(text)
                if text in seen:
                    continue
                seen.add(text)
                rows.append({"id": f"gs-{len(rows):04d}", "label": label, "family": family, "monologue": True,
                             "turns": [["Người gọi", text]],
                             "split": "validation" if family in VALIDATION_FAMILIES else "train"})
    return rows


def main() -> int:
    """Sinh dữ liệu và ghi ra file. Hai tham số tùy chọn: số đoạn mỗi kịch bản bình thường và mỗi kịch bản lừa đảo."""
    counts = [int(value) for value in sys.argv[1:3]]
    rows = generate(*counts)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n").encode("utf-8"))
    normal = sum(1 for row in rows if row["label"] == 0)
    held = sum(1 for row in rows if row["split"] == "validation")
    words = sorted(len(row["turns"][0][1].split()) for row in rows)
    print(f"wrote {OUT}: {len(rows)} rows ({normal} normal, {len(rows) - normal} scam; {held} for validation); "
          f"words min {words[0]} median {words[len(words) // 2]} max {words[-1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
