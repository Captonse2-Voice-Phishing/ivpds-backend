"""Sinh thêm hội thoại bối cảnh Việt Nam cho huấn luyện, từ các kịch bản bổ sung (đợt 6).

Cách dùng (chạy từ thư mục ``ai``):

    python -m tools.dataset_synthesize_vi_more

Các kịch bản ở đây bổ sung cho ``dataset_synthesize_vi.py``: hãng bay, tòa án, phạt nguội, tình cảm qua mạng, giả
sếp, xuất khẩu lao động, đặt bàn, đặt phòng, từ thiện, máy lọc nước, phòng cháy chữa cháy, trúng tuyển, bán thuốc...
và các cuộc bình thường cùng chủ đề. Mỗi kịch bản sinh ``PER_FAMILY`` biến thể bằng cách đổi cách nói, cách xưng hô
và chi tiết. Kết quả ghi vào ``data/synthetic/vi_generated_more.jsonl``, cùng định dạng với ``vi_generated.jsonl``;
``tools.dataset_prepare`` đọc cả hai file.

Bộ này ban đầu (10/10/2026) được viết làm bộ test; theo yêu cầu của người dùng nó được chuyển sang huấn luyện,
nên kết quả test cũ trên ``generated_test_calls.jsonl`` không còn dùng để đánh giá các model huấn luyện từ đợt 6.
"""

import json
import random
import sys
from pathlib import Path

from tools.dataset_synthesize_vi import FILLERS, PRONOUNS, SPEAKER_STYLES, T, _fill

OUT = Path("data/synthetic/vi_generated_more.jsonl")
SEED = 20261010
PER_FAMILY = 40

# Phản ứng của người nghe, viết riêng cho các kịch bản bổ sung.
WARY = ["Nghe cứ sao sao ấy, có đúng không vậy?", "Khoan đã, {v} chưa hiểu lắm.", "Việc này {v} phải xem lại đã.",
        "Sao gấp thế, để {v} kiểm tra lại.", "{V} hơi lo, có cách nào khác không?"]
OKAY = ["Ừ được rồi.", "Vâng, {v} biết rồi.", "Thế thì tốt quá.", "Rồi, {v} nhớ rồi.", "Vâng, hẹn gặp lại nhé."]

SCAM = {
    "giả hãng bay hủy chuyến": [
        T("C", ["Chào {y}, {m} gọi từ hãng hàng không, chuyến bay đi {city} của {y} vừa bị hủy.",
                "{M} là nhân viên phòng vé, vé đi {city} của {y} gặp sự cố xuất vé.",
                "Hãng hàng không xin thông báo chuyến bay của {y} vào {day} không còn khai thác."]),
        T("V", ["Sao lại hủy?", "Vậy vé của {v} thế nào?", "Giờ phải làm sao?"]),
        T("C", ["{M} đổi vé cho {y} ngay, {y} đọc số thẻ thanh toán, ngày hết hạn và mã ba số mặt sau.",
                "Để hoàn tiền {y} bấm vào đường link {m} gửi rồi nhập thông tin thẻ.",
                "{Y} chuyển thêm {small} phí đổi chuyến vào tài khoản cá nhân của {m} để giữ chỗ."]),
        T("V", WARY, 0.7),
        T("C", ["Lát có mã gửi về máy {y} đọc luôn cho {m}, {m} chỉ giữ chỗ được mười phút.",
                "Không làm {deadline} là {y} mất toàn bộ tiền vé.", "{Y} làm ngay đi kẻo hết chuyến thay thế."]),
    ],
    "giả tòa án báo nợ thẻ": [
        T("C", ["Đây là tòa án nhân dân, {y} có một giấy triệu tập chưa nhận.",
                "Tòa án xin thông báo {y} đang bị khởi kiện vì nợ thẻ tín dụng {amt}.",
                "Tôi là thư ký tòa, hồ sơ của {y} sẽ bị xử vắng mặt vào {day}."]),
        T("V", ["{V} có nợ thẻ nào đâu.", "Triệu tập về việc gì?", "Chắc nhầm người rồi."]),
        T("C", ["Vậy là thông tin của {y} bị đánh cắp, tôi chuyển máy cho cơ quan điều tra, {y} không được tắt máy.",
                "{Y} đọc số căn cước và các tài khoản ngân hàng đang dùng để tòa đối chiếu.",
                "{Y} phải kê khai toàn bộ số dư rồi chuyển sang tài khoản phong tỏa của viện kiểm sát."]),
        T("V", WARY, 0.6),
        T("C", ["Việc này là mật, {y} không được trao đổi với người nhà.",
                "Không hợp tác {deadline} thì tài sản của {y} bị kê biên.",
                "{Y} chuyển ngay, xác minh xong sẽ trả lại trong hai mươi bốn giờ."]),
    ],
    "giả cảnh sát giao thông phạt nguội": [
        T("C", ["Tôi là cán bộ đội cảnh sát giao thông, xe của {y} có một biên bản phạt nguội quá hạn.",
                "Phòng cảnh sát giao thông thông báo {y} có lỗi vi phạm chưa xử lý từ tháng trước.",
                "Hệ thống ghi nhận xe của {y} gây tai nạn rồi rời khỏi hiện trường."]),
        T("V", ["{V} có vi phạm gì đâu.", "Lỗi gì vậy?", "Xe {v} mấy hôm nay để ở nhà mà."]),
        T("C", ["Hôm nay không nộp thì hồ sơ chuyển sang truy tố, {y} chuyển {amt} tiền phạt vào tài khoản tôi đọc.",
                "{Y} cài ứng dụng xử phạt theo đường link tôi gửi qua {app} rồi đăng nhập ngân hàng để nộp.",
                "{Y} đọc số căn cước, số giấy phép lái xe và số tài khoản để tôi lập biên bản điện tử."]),
        T("V", WARY, 0.6),
        T("C", ["{Y} giữ máy cho đến khi chuyển xong.", "Chậm là bị tước bằng và tạm giữ xe.",
                "{Y} làm {deadline}, đây là lần nhắc cuối."]),
    ],
    "tình cảm qua mạng xin tiền": [
        T("C", ["Em à, anh đây, kiện quà anh gửi cho em đang bị hải quan giữ.",
                "Em ơi anh đang kẹt ở sân bay, thẻ của anh bị khóa hết rồi.",
                "Anh sắp về Việt Nam gặp em nhưng tài khoản ở nước ngoài của anh bị phong tỏa."]),
        T("V", ["Sao lại bị giữ?", "Trời, giờ anh tính sao?", "Em có giúp được gì không?"]),
        T("C", ["Em chuyển giúp anh {amt} tiền thuế thông quan vào tài khoản của nhân viên hải quan nhé.",
                "Em chuyển tạm cho anh {amt}, sang tuần anh gửi lại gấp đôi.",
                "Luật sư bảo cần {amt} phí giải tỏa, em chuyển vào số tài khoản anh nhắn."]),
        T("V", ["Nhiều thế em lấy đâu ra.", "Để em hỏi chị em đã.", "Mình chưa gặp nhau lần nào mà anh."], 0.7),
        T("C", ["Em đừng nói với ai, người ta không hiểu chuyện của mình đâu.",
                "Em vay tạm ai đó đi, anh cần {deadline}.", "Em không tin anh sao, chuyển ngay giúp anh đi."]),
    ],
    "giả sếp yêu cầu chuyển khoản": [
        T("C", ["Em ơi anh giám đốc đây, anh đang họp với đối tác không nghe máy được lâu.",
                "Chị kế toán à, sếp đây, số này là số mới của sếp.",
                "Em là kế toán công ty phải không, anh đang đi công tác, có việc gấp."]),
        T("V", ["Dạ sếp nói đi ạ.", "Vâng em nghe.", "Dạ có việc gì ạ?"]),
        T("C", ["Em chuyển ngay {big} cho đối tác theo số tài khoản anh nhắn, hợp đồng anh bổ sung sau.",
                "Em ứng trước {amt} vào tài khoản cá nhân này cho anh, mai anh ký duyệt.",
                "Chuyển gấp {big} tiền đặt cọc, đừng báo ai trong công ty vì việc này đang bảo mật."]),
        T("V", ["Dạ nhưng chưa có giấy đề nghị ạ.", "Để em báo trưởng phòng đã.", "Số tiền lớn quá sếp ạ."], 0.7),
        T("C", ["Không kịp đâu, em làm ngay, anh chịu trách nhiệm.", "Chậm là mất hợp đồng, em chuyển {deadline}.",
                "Đừng gọi lại số cũ của anh, anh đang không dùng."]),
    ],
    "xuất khẩu lao động đóng phí": [
        T("C", ["Chào {y}, {m} bên công ty xuất khẩu lao động, hồ sơ đi Nhật của {y} đã trúng tuyển.",
                "{M} là tư vấn viên du học nghề, {y} được chọn đi Hàn Quốc không cần thi tiếng.",
                "Công ty cung ứng nhân lực thông báo {y} có suất đi Đức lương {amt} một tháng."]),
        T("V", ["Thật à, bao giờ đi?", "Cần chuẩn bị gì?", "Chi phí thế nào?"]),
        T("C", ["{Y} chuyển trước {amt} phí giữ suất và làm visa vào tài khoản của {m}.",
                "{Y} đóng {amt} tiền đặt cọc chống trốn {deadline}, không cần lên công ty.",
                "Suất này chỉ còn hai người, {y} chuyển khoản ngay để {m} nộp hồ sơ lên đại sứ quán."]),
        T("V", WARY, 0.6),
        T("C", ["Không đóng hôm nay là suất chuyển cho người khác.", "Hợp đồng {m} gửi sau khi nhận tiền.",
                "{Y} cứ chuyển đi, bay trong tháng sau."]),
    ],
    "giả ngân hàng báo có người vay tên mình": [
        T("C", ["Chào {y}, {m} gọi từ {bank}, có một khoản vay {amt} vừa được giải ngân dưới tên {y}.",
                "{M} bên bộ phận tín dụng {bank}, hệ thống ghi nhận {y} vừa vay online {amt}.",
                "Ngân hàng {bank} thông báo khoản vay của {y} đã quá hạn thanh toán kỳ đầu."]),
        T("V", ["{V} có vay gì đâu.", "Ai vay?", "Chắc có người mạo danh rồi."]),
        T("C", ["Để hủy khoản vay {y} chuyển lại đúng số tiền đó vào tài khoản tất toán {m} đọc.",
                "{Y} đọc mã xác nhận ngân hàng vừa gửi để {m} khóa khoản vay.",
                "{Y} cài phần mềm {remote} để kỹ thuật viên vào máy hủy lệnh vay."]),
        T("V", WARY, 0.6),
        T("C", ["Không hủy {deadline} thì {y} phải trả cả gốc lẫn lãi.", "Chậm là {y} bị ghi nợ xấu.",
                "{Y} làm ngay, {m} đang giữ lệnh trên hệ thống."]),
    ],
    "giả định danh điện tử": [
        T("C", ["Cháu là công an khu vực, tài khoản định danh điện tử của {y} đang bị lỗi dữ liệu.",
                "Tôi là cán bộ quản lý cư trú, {y} cần nâng cấp định danh mức hai trong hôm nay.",
                "Công an phường thông báo căn cước gắn chíp của {y} chưa đồng bộ, sắp bị khóa."]),
        T("V", ["Bị khóa thì sao?", "Làm ở đâu?", "{V} không rành mấy cái này."]),
        T("C", ["{Y} không cần ra phường, bấm đường link gửi qua {app} để tải ứng dụng dịch vụ công.",
                "{Y} cài ứng dụng theo link, cho phép hết các quyền rồi nhập mật khẩu ngân hàng để đồng bộ.",
                "{Y} đưa mặt vào camera và đọc mã gửi về điện thoại cho tôi."]),
        T("V", WARY, 0.6),
        T("C", ["Không làm {deadline} là không rút được lương hưu.", "Ứng dụng này không có trên kho, {y} cứ bấm link.",
                "{Y} làm ngay, tôi hướng dẫn từng bước."]),
    ],
    "giả phòng khám báo kết quả xấu": [
        T("C", ["Phòng khám đa khoa xin nghe, kết quả xét nghiệm của {y} có dấu hiệu rất nghiêm trọng.",
                "{M} gọi từ bệnh viện, phim chụp của {y} phát hiện khối u cần xử lý gấp.",
                "Bác sĩ nhờ {m} báo {y} phải làm gói tầm soát đặc biệt ngay tuần này."]),
        T("V", ["Trời, nghiêm trọng thế nào?", "Có chắc không em?", "Vậy phải làm gì?"]),
        T("C", ["{Y} đặt cọc {amt} giữ suất, chuyển vào tài khoản {m} đọc bây giờ.",
                "Thuốc đặc trị phải đặt từ nước ngoài, {y} chuyển trước {amt}.",
                "{Y} chuyển {amt} viện phí tạm ứng thì bác sĩ mới xếp lịch."]),
        T("V", ["Để mai {v} lên viện rồi đóng.", "{V} muốn gặp bác sĩ trước."], 0.7),
        T("C", ["Suất chỉ giữ ba mươi phút, {y} chuyển liền đi.", "{Y} đừng nói với người nhà kẻo mọi người lo.",
                "Để chậm bệnh nặng thêm thì bên {m} không chịu trách nhiệm."]),
    ],
    "giả bảo hiểm trả lãi đóng phí trước": [
        T("C", ["Chào {y}, {m} bên công ty bảo hiểm, hợp đồng của {y} được chia lãi đặc biệt {amt}.",
                "{M} là tư vấn viên bảo hiểm, {y} được hoàn phí {amt} do chương trình tri ân.",
                "Công ty bảo hiểm thông báo hợp đồng cũ của {y} còn một khoản {amt} chưa nhận."]),
        T("V", ["Nhận thế nào?", "Thật à?", "{V} tưởng hợp đồng hết hạn rồi."]),
        T("C", ["Để nhận {y} đóng trước {small} thuế thu nhập và phí giải ngân vào tài khoản của {m}.",
                "{Y} đọc số thẻ ngân hàng và mã gửi về máy để {m} chuyển tiền.",
                "{Y} chuyển {small} phí mở hồ sơ rồi {m} làm lệnh chi ngay."]),
        T("V", ["Sao không trừ thẳng vào tiền lãi?", "Phải đóng trước à?"], 0.7),
        T("C", ["Quy định là đóng trước, hôm nay là hạn chót.", "Không làm {deadline} là mất quyền lợi.",
                "{Y} chuyển ngay giúp {m}."]),
    ],
    "giả dịch vụ xóa nợ xấu": [
        T("C", ["Chào {y}, {m} bên trung tâm tín dụng, {y} đang có nợ xấu nhóm năm trên hệ thống.",
                "{M} làm dịch vụ xóa nợ xấu, cam kết sạch lịch sử tín dụng trong ba ngày.",
                "Hồ sơ của {y} đang bị chặn vay ở mọi ngân hàng, bên {m} xử lý được."]),
        T("V", ["Xóa được thật à?", "Làm thế nào?", "Phí bao nhiêu?"]),
        T("C", ["{Y} chuyển trước {amt} phí can thiệp hệ thống, xong việc mới thu phần còn lại.",
                "{Y} gửi ảnh căn cước, số tài khoản và mật khẩu ngân hàng điện tử để bên {m} thao tác.",
                "{Y} đóng {small} phí hồ sơ {deadline} để giữ suất xử lý trong tháng."]),
        T("V", WARY, 0.6),
        T("C", ["Bên {m} có người trong ngân hàng nhà nước nên {y} yên tâm.", "Không làm bây giờ thì sang tháng không xóa được.",
                "{Y} chuyển khoản đi, {m} gửi biên nhận qua {app}."]),
    ],
    "giả nâng hạn mức thẻ tín dụng": [
        T("C", ["Chào {y}, {m} gọi từ trung tâm thẻ {bank}, thẻ của {y} được nâng hạn mức lên {amt}.",
                "{M} bên {bank}, {y} được miễn phí thường niên và nâng hạn mức ngay hôm nay.",
                "Trung tâm thẻ thông báo {y} được hoàn tiền {small} cho các giao dịch tháng trước."]),
        T("V", ["Ừ thế thì tốt.", "Làm thế nào em?", "Có mất phí không?"]),
        T("C", ["{M} làm luôn qua điện thoại, {y} đọc mười sáu số trên thẻ và ngày hết hạn.",
                "{Y} đọc ba số bảo mật mặt sau thẻ để {m} xác thực.",
                "Hệ thống vừa gửi mã về máy {y}, {y} đọc lại cho {m} trong một phút."]),
        T("V", ["Phải đọc cả số thẻ à?", "Để {v} lấy thẻ đã."], 0.7),
        T("C", ["Mã sắp hết hiệu lực, {y} đọc nhanh giúp {m}.", "Chỉ làm được trong hôm nay thôi ạ.",
                "{Y} đọc tiếp mã thứ hai vừa gửi để hoàn tất."]),
    ],
    "giả đổi sim 5G": [
        T("C", ["Chào {y}, {m} gọi từ {telco}, {m} hỗ trợ {y} nâng cấp sim lên năm gờ miễn phí.",
                "{M} là nhân viên {telco}, sim của {y} sắp không dùng được do tắt sóng cũ.",
                "Tổng đài {telco} mời {y} đổi sim công nghệ mới ngay qua điện thoại."]),
        T("V", ["Đổi thế nào?", "Có phải ra cửa hàng không?", "Mất tiền không em?"]),
        T("C", ["Không cần ra cửa hàng, {y} soạn tin theo cú pháp có dãy số {m} đọc rồi gửi lên tổng đài.",
                "{Y} đọc mã {telco} vừa gửi về máy cho {m} để kích hoạt sim mới.",
                "{Y} bấm vào đường link {m} nhắn rồi nhập số căn cước và mã xác nhận."]),
        T("V", WARY, 0.6),
        T("C", ["Máy sẽ mất sóng vài tiếng, trong lúc đó {y} đừng liên hệ ai.", "Có mã nào về {y} đọc hết cho {m} nhé.",
                "{Y} làm {deadline} kẻo sim bị khóa."]),
    ],
    "giả cấp nước cài ứng dụng": [
        T("C", ["Chào {y}, {m} bên công ty cấp nước, nhà {y} đang nợ hai kỳ tiền nước.",
                "Công ty nước sạch thông báo chiều nay sẽ cắt nước nhà {y}.",
                "{M} là nhân viên cấp nước, đồng hồ nhà {y} sai chỉ số nên bị truy thu {small}."]),
        T("V", ["Nhà {v} đóng đủ mà.", "Sao lại cắt?", "Truy thu gì vậy?"]),
        T("C", ["{Y} kết bạn {app} với số này, cài ứng dụng cấp nước theo link rồi thanh toán trong đó.",
                "{Y} chuyển khoản ngay vào tài khoản cá nhân của nhân viên thu ngân.",
                "{Y} bấm cho phép cài từ nguồn lạ rồi đăng nhập ngân hàng trong ứng dụng."]),
        T("V", WARY, 0.6),
        T("C", ["Đội thi công đang trên đường, {y} làm trước bốn giờ chiều.", "Không thanh toán {deadline} là tháo đồng hồ.",
                "{Y} làm nhanh kẻo phải đóng phí mở nước lại."]),
    ],
    "giả bảo hành điện máy thu phí": [
        T("C", ["Chào {y}, {m} bên trung tâm bảo hành, cái tủ lạnh nhà {y} thuộc lô bị lỗi cần thu hồi.",
                "{M} gọi từ hãng điện máy, sản phẩm {y} mua được đền bù {amt}.",
                "Trung tâm bảo hành thông báo máy giặt nhà {y} được gia hạn bảo hành năm năm."]),
        T("V", ["Thế à, đền bù kiểu gì?", "Nhà {v} có mua thật.", "Phải làm gì?"]),
        T("C", ["Để nhận tiền {y} bấm đường link {m} gửi rồi nhập số thẻ và mã ngân hàng gửi về.",
                "{Y} chuyển trước {small} phí kích hoạt gói bảo hành vào tài khoản của {m}.",
                "{Y} đọc số tài khoản, số thẻ và mã xác nhận để kế toán chuyển tiền đền bù."]),
        T("V", WARY, 0.6),
        T("C", ["Chương trình chỉ áp dụng trong hôm nay.", "{Y} làm trong mười phút kẻo hết lượt.",
                "{Y} đọc mã ngay giúp {m} để hệ thống ghi nhận."]),
    ],
    "giả đại lý vé máy bay giá rẻ": [
        T("C", ["Chào {y}, {m} bên đại lý vé, {y} hỏi vé đi {city} dịp lễ đúng không ạ?",
                "{M} thấy {y} đăng tìm vé máy bay, bên {m} còn vé giá bằng một nửa hãng.",
                "Đại lý vé xin báo {y} được suất vé khuyến mãi đi {city} chỉ {small}."]),
        T("V", ["Ừ, còn vé không em?", "Rẻ vậy à?", "Giữ chỗ thế nào?"]),
        T("C", ["{Y} chuyển khoản toàn bộ tiền vé vào tài khoản cá nhân của {m}, {m} gửi mã đặt chỗ sau.",
                "Vé chỉ giữ được mười lăm phút, {y} chuyển {amt} ngay.",
                "{Y} chuyển cọc {small} trước, không xuất hóa đơn vì là vé nội bộ."]),
        T("V", ["Cho {v} xem mã đặt chỗ trước được không?", "Sao không thanh toán trên trang của hãng?"], 0.7),
        T("C", ["Mã chỉ có sau khi nhận tiền ạ.", "Còn đúng hai vé thôi, {y} chuyển {deadline}.",
                "Chuyển xong {y} chụp màn hình gửi {m}."]),
    ],
    "giả chuyển nhầm tiền đòi lại": [
        T("C", ["Chào {y}, {m} vừa chuyển nhầm {amt} vào tài khoản của {y}.",
                "Alo, {m} bên công ty tài chính, {y} vừa nhận {amt} từ bên {m} đúng không?",
                "{Y} ơi {m} chuyển khoản nhầm số, {y} kiểm tra giúp {m} với."]),
        T("V", ["Để {v} xem.", "{V} có thấy tiền vào thật.", "Vậy giờ làm sao?"]),
        T("C", ["Đó là khoản vay đã giải ngân cho {y}, giờ {y} phải trả cả gốc và lãi {amt} trong tuần.",
                "{Y} chuyển lại vào số tài khoản khác {m} đọc, kèm {small} phí xử lý.",
                "{Y} bấm vào đường link hoàn tiền {m} gửi rồi nhập mật khẩu ngân hàng và mã gửi về."]),
        T("V", WARY, 0.6),
        T("C", ["Không trả {deadline} bên {m} sẽ cho người đến nhà.", "Chậm một ngày lãi tăng thêm {small}.",
                "{Y} làm ngay kẻo bị báo công an vì chiếm giữ tiền."]),
    ],
}

NORMAL = {
    "hãng bay báo đổi giờ": [
        T("C", ["Chào {y}, {m} gọi từ hãng hàng không, chuyến bay đi {city} của {y} đổi giờ cất cánh.",
                "Hãng hàng không xin báo chuyến đi {city} vào {day} của {y} bay muộn hơn một tiếng.",
                "{M} bên hãng bay, chuyến của {y} đổi sang cửa ra máy bay khác."]),
        T("V", ["Có phải đổi vé không?", "Bay lúc mấy giờ?", "Vé của {v} còn dùng được chứ?"]),
        T("C", ["Không cần ạ, vé vẫn giữ nguyên, hãng đã gửi hành trình mới qua email.",
                "Giờ mới là {hour}, {y} ra sân bay sớm hai tiếng như bình thường.",
                "Vé vẫn dùng được, {y} xem cửa ra máy bay trên bảng điện tử ở sân bay."]),
        T("V", ["Muốn đổi chuyến khác thì sao?", "Vâng {v} biết rồi."], 0.7),
        T("C", ["{Y} vào mục quản lý đặt chỗ trên trang web của hãng, lần này đổi không mất phí.",
                "Dạ {m} cảm ơn {y}.", "Chúc {y} chuyến bay tốt đẹp."]),
    ],
    "tòa án xác nhận người làm chứng": [
        T("C", ["Chào {y}, tôi là thư ký tòa án quận, {y} là người làm chứng trong một vụ tranh chấp hợp đồng.",
                "Tòa án quận gọi xác nhận {y} đã nhận giấy triệu tập gửi qua bưu điện chưa.",
                "Tôi gọi từ tòa án về phiên hòa giải {day} mà {y} được mời tham dự."]),
        T("V", ["{V} nhận được rồi.", "Phiên ngày nào?", "Cần mang gì không?"]),
        T("C", ["{Y} mang giấy triệu tập và căn cước, đến phòng xử số ba lúc {hour}.",
                "Phiên vào {day}, {y} có mặt trước mười lăm phút.",
                "{Y} chỉ cần có mặt, tòa không thu khoản phí nào."]),
        T("V", ["Nếu bận thì sao?", "Vâng {v} sẽ đến."], 0.7),
        T("C", ["{Y} làm đơn xin vắng mặt nộp tại tòa trước ngày xử.", "Vâng, cảm ơn {y}.", "Hẹn {y} tại tòa."]),
    ],
    "cảnh sát giao thông mời lên trụ sở": [
        T("C", ["Tôi là cán bộ đội cảnh sát giao thông quận, xe của {y} có một lỗi ghi nhận qua camera.",
                "Đội cảnh sát giao thông thông báo {y} có thông báo vi phạm đã gửi về địa chỉ đăng ký xe.",
                "Tôi gọi nhắc {y} đến giải quyết thông báo phạt nguội đã gửi tuần trước."]),
        T("V", ["Lỗi gì vậy?", "{V} phải đến đâu?", "Nộp phạt thế nào?"]),
        T("C", ["{Y} mang giấy tờ xe và căn cước đến trụ sở đội trong giờ hành chính để xem hình ảnh.",
                "Sau khi có quyết định xử phạt {y} nộp tại kho bạc hoặc trên cổng dịch vụ công.",
                "{Y} đến trực tiếp, chúng tôi không thu tiền qua điện thoại."]),
        T("V", ["{Day} {v} đến được không?", "Vâng."], 0.7),
        T("C", ["Được, đội làm việc cả tuần trừ chủ nhật.", "Vâng, chào {y}.", "{Y} nhớ mang bản gốc giấy tờ."]),
    ],
    "người yêu hẹn nhau": [
        T("C", ["Em à, tối nay mình đi ăn nhé, anh vừa nhận lương.", "Anh ơi cuối tuần mình về quê em chơi không?",
                "Em ơi anh đặt được vé xem phim suất {hour} rồi."]),
        T("V", ["Ừ, mấy giờ anh qua?", "Được đó, đi xe gì?", "Phim gì vậy anh?"]),
        T("C", ["{Hour} anh qua đón, em muốn ăn lẩu hay ăn nướng?", "Mình đi xe khách, anh đặt vé rồi, hết {small}.",
                "Phim hài mới ra, vé anh thanh toán qua ví rồi."]),
        T("V", ["Ăn lẩu đi, để em chia tiền với anh.", "Em chuyển lại anh tiền vé nhé.", "Thế em mua bắp nước."], 0.8),
        T("C", ["Thôi anh mời, hôm khác em mời lại.", "Ừ cũng được, lát em chuyển sau.", "Ok, hẹn em tối nay."]),
    ],
    "sếp giao việc cho nhân viên": [
        T("C", ["Em ơi anh trưởng phòng đây, báo cáo doanh thu tháng này xong chưa?",
                "Chị kế toán ơi, hóa đơn của nhà cung cấp đã có đủ chữ ký chưa?",
                "Em à, hợp đồng với đối tác ở {city} anh duyệt trên hệ thống rồi."]),
        T("V", ["Dạ em gửi trong chiều nay ạ.", "Dạ còn thiếu chữ ký giám đốc.", "Vâng em thấy rồi ạ."]),
        T("C", ["Ừ, em gửi qua email công ty, mai họp lúc {hour}.",
                "Thế em trình ký xong rồi mới làm lệnh thanh toán theo đúng quy trình nhé.",
                "Em làm đề nghị thanh toán, có đủ phê duyệt thì kế toán mới chuyển khoản."]),
        T("V", ["Dạ vâng ạ.", "Dạ em làm ngay."], 0.8),
        T("C", ["Cảm ơn em.", "Không cần gấp, cuối tuần xong là được.", "Có gì vướng em báo anh."]),
    ],
    "công ty xuất khẩu lao động hẹn làm hồ sơ": [
        T("C", ["Chào {y}, {m} bên công ty xuất khẩu lao động, {y} đăng ký buổi tư vấn {day} đúng không ạ?",
                "{M} gọi nhắc lịch thi tuyển đơn hàng đi Nhật của {y} vào {day}.",
                "Công ty mời {y} lên văn phòng nhận kết quả khám sức khỏe."]),
        T("V", ["Đúng rồi em.", "Thi ở đâu?", "Cần mang gì?"]),
        T("C", ["{Y} mang căn cước và bằng tốt nghiệp lên văn phòng lúc {hour}.",
                "Thi tại trụ sở công ty, {y} xem địa chỉ trên giấy phép đăng trên cổng của bộ lao động.",
                "Mọi khoản phí chỉ đóng tại quầy sau khi ký hợp đồng, có phiếu thu đỏ."]),
        T("V", ["Có phải đóng tiền trước không?", "Vâng {v} sẽ lên."], 0.7),
        T("C", ["Dạ không ạ, buổi tư vấn miễn phí.", "Dạ {m} hẹn {y}.", "Dạ chưa đóng gì cho đến khi trúng tuyển ạ."]),
    ],
    "ngân hàng xác nhận tất toán tại quầy": [
        T("C", ["Chào {y}, {m} gọi từ {bank}, khoản vay của {y} đến hạn tất toán vào {day}.",
                "{M} bên {bank}, {y} đã đặt lịch tất toán sổ tiết kiệm tại chi nhánh.",
                "Ngân hàng {bank} gọi xác nhận lịch hẹn ký phụ lục hợp đồng vay của {y}."]),
        T("V", ["Ừ đúng rồi.", "Cần mang gì em?", "Mấy giờ làm việc?"]),
        T("C", ["{Y} mang căn cước và hợp đồng vay ra quầy, nhân viên tính số tiền chính xác tại chỗ.",
                "{Y} mang sổ và căn cước, chi nhánh mở cửa đến {hour}.",
                "{Y} ký trực tiếp tại quầy, {m} không cần thông tin gì qua điện thoại."]),
        T("V", ["Có chuyển khoản trước được không?", "Vâng {v} ra."], 0.7),
        T("C", ["Dạ {y} tự thanh toán trong ứng dụng ngân hàng cũng được ạ.", "Dạ {m} cảm ơn {y}.", "Dạ hẹn {y} tại chi nhánh."]),
    ],
    "phường mời họp tổ dân phố": [
        T("C", ["Chào {y}, tôi là tổ trưởng tổ dân phố, {day} tổ mình họp ở nhà văn hóa.",
                "Ủy ban phường mời hộ nhà {y} đi tiêm phòng cho trẻ vào {day}.",
                "Tôi gọi báo phường đang làm định danh điện tử cho bà con tại nhà văn hóa."]),
        T("V", ["Mấy giờ họp?", "Cần mang gì?", "Có mất phí không?"]),
        T("C", ["{Hour} bắt đầu, bàn về đóng góp làm đường, ai đóng thì nộp cho thủ quỹ có biên lai.",
                "{Y} mang sổ tiêm và căn cước, tiêm miễn phí.",
                "Miễn phí, {y} mang căn cước và điện thoại, cán bộ làm trực tiếp."]),
        T("V", OKAY),
        T("C", ["Vâng, mời {y} đến đúng giờ.", "Cảm ơn {y}.", "Ai gọi bảo bấm link cài ứng dụng thì {y} đừng nghe nhé."], 0.6),
    ],
    "trung tâm tiếng Anh báo lịch học": [
        T("C", ["Chào phụ huynh, em gọi từ trung tâm tiếng Anh, lớp của bé chuyển sang {day}.",
                "Trung tâm ngoại ngữ xin báo học phí khóa mới của bé là {amt}.",
                "Em là trợ giảng của bé, em gọi báo kết quả kiểm tra giữa khóa."]),
        T("V", ["Mấy giờ học em?", "Đóng thế nào?", "Bé học sao rồi?"]),
        T("C", ["Lớp học lúc {hour}, phòng vẫn như cũ ạ.",
                "Phụ huynh đóng tại quầy lễ tân hoặc chuyển khoản vào tài khoản công ty in trên phiếu thu.",
                "Bé tiến bộ nhiều, phần nghe cần luyện thêm ạ."]),
        T("V", OKAY),
        T("C", ["Dạ em cảm ơn phụ huynh.", "Hạn đóng đến cuối tháng ạ.", "Em gửi bài tập thêm qua nhóm lớp nhé."], 0.6),
    ],
    "gara báo sửa xe xong": [
        T("C", ["Chào {y}, gara đây, xe của {y} sửa xong rồi.", "{M} bên gara, xe {y} cần thay thêm má phanh.",
                "Xưởng sửa xe báo xe của {y} bảo dưỡng xong, {y} qua lấy được rồi."]),
        T("V", ["Hết bao nhiêu em?", "Thay thêm mất bao nhiêu?", "Chiều {v} qua."]),
        T("C", ["Tổng cộng {amt}, {y} qua xem xe rồi thanh toán tại quầy.", "Thêm {small}, {y} đồng ý thì {m} mới thay.",
                "Gara mở cửa đến {hour}, có hóa đơn đầy đủ."]),
        T("V", ["Chuyển khoản được không?", "Ừ thay đi."], 0.8),
        T("C", ["Được ạ, khi {y} đến nhận xe quét mã ở quầy.", "Dạ vâng.", "Dạ {m} cảm ơn {y}."]),
    ],
    "ngân hàng mời nâng hạn mức tự làm": [
        T("C", ["Chào {y}, {m} gọi từ trung tâm thẻ {bank}, thẻ của {y} đủ điều kiện nâng hạn mức.",
                "{M} bên {bank}, {y} được ưu đãi miễn phí thường niên năm sau.",
                "Trung tâm thẻ {bank} mời {y} mở thêm thẻ phụ cho người thân."]),
        T("V", ["Có mất phí không?", "Làm thế nào?", "Em làm luôn được không?"]),
        T("C", ["Không mất phí, nếu đồng ý {y} tự xác nhận trong ứng dụng ngân hàng, mục thẻ.",
                "Ưu đãi tự áp dụng, {y} không cần làm gì thêm.",
                "{Y} ra chi nhánh mang căn cước của hai người để đăng ký."]),
        T("V", ["Em không làm thay được à?", "Ừ để {v} xem."], 0.7),
        T("C", ["Dạ không ạ, bên {m} không thao tác thay và không hỏi số thẻ hay mã qua điện thoại.",
                "Dạ {m} cảm ơn {y}.", "Dạ có gì {y} gọi tổng đài in sau thẻ."]),
    ],
    "nhà mạng mời đổi sim tại cửa hàng": [
        T("C", ["Chào {y}, {m} gọi từ {telco}, sim của {y} nên đổi sang loại mới để dùng mạng nhanh hơn.",
                "{M} là nhân viên {telco}, khu vực của {y} sắp tắt sóng cũ.",
                "Tổng đài {telco} thông báo chương trình đổi sim miễn phí đến hết tháng."]),
        T("V", ["Đổi ở đâu?", "Mất tiền không?", "Làm qua điện thoại được không?"]),
        T("C", ["{Y} mang căn cước ra cửa hàng {telco} gần nhất, đổi trong năm phút.",
                "Miễn phí ạ, {y} giữ nguyên số.",
                "Dạ không, phải ra cửa hàng vì cần đối chiếu căn cước trực tiếp."]),
        T("V", OKAY),
        T("C", ["Dạ {m} cảm ơn {y}.", "Cửa hàng mở đến {hour}.", "Bên {m} không yêu cầu đọc mã nào qua điện thoại đâu ạ."], 0.6),
    ],
    "cấp nước hẹn thay đồng hồ": [
        T("C", ["Chào {y}, {m} bên công ty cấp nước, tuần sau bên {m} thay đồng hồ định kỳ cho khu nhà {y}.",
                "Công ty nước sạch báo {day} khu phố mình tạm ngừng cấp nước để sửa ống.",
                "{M} gọi hẹn lịch kiểm tra đồng hồ nước nhà {y}."]),
        T("V", ["Thay có mất tiền không?", "Ngừng đến mấy giờ?", "{Day} được không?"]),
        T("C", ["Không mất phí, công ty chi trả hết.", "Ngừng từ sáng đến {hour}, {y} trữ nước trước nhé.",
                "Được ạ, nhân viên mặc đồng phục và có thẻ tên."]),
        T("V", OKAY),
        T("C", ["Dạ {m} cảm ơn {y}.", "Tiền nước {y} vẫn đóng như mọi tháng.", "{Y} cứ kiểm tra thẻ trước khi cho vào nhà."], 0.6),
    ],
    "bảo hành điện máy hẹn lịch": [
        T("C", ["Chào {y}, {m} bên trung tâm bảo hành, {y} báo máy giặt bị lỗi đúng không ạ?",
                "{M} gọi hẹn lịch kỹ thuật viên đến kiểm tra tủ lạnh nhà {y}.",
                "Trung tâm bảo hành báo linh kiện thay cho điều hòa nhà {y} đã về."]),
        T("V", ["Đúng rồi em.", "Bao giờ đến?", "Có mất phí không?"]),
        T("C", ["Kỹ thuật viên đến vào {day} lúc {hour}, máy còn bảo hành nên không mất phí.",
                "{Day} bên {m} qua, {y} chuẩn bị phiếu bảo hành giúp.",
                "Nếu hết bảo hành thì thợ báo giá tại nhà, {y} đồng ý mới sửa."]),
        T("V", OKAY),
        T("C", ["Dạ {m} cảm ơn {y}.", "Thợ sẽ gọi trước khi đến.", "Thanh toán thì có hóa đơn của hãng ạ."], 0.6),
    ],
    "đại lý vé xác nhận đặt chỗ": [
        T("C", ["Chào {y}, {m} bên phòng vé, vé đi {city} {y} đặt sáng nay đã xuất xong.",
                "{M} gọi xác nhận {y} đặt hai vé đi {city} vào {day}.",
                "Phòng vé báo chuyến {y} hỏi còn chỗ, giá {amt}."]),
        T("V", ["Mã đặt chỗ là gì em?", "Đúng rồi.", "Thanh toán thế nào?"]),
        T("C", ["{M} đã gửi mã đặt chỗ và vé điện tử qua email, {y} kiểm tra trên trang của hãng được.",
                "Vậy {m} giữ chỗ đến {hour}, {y} thanh toán sau khi nhận mã đặt chỗ.",
                "{Y} chuyển vào tài khoản công ty ghi trên hóa đơn hoặc ghé văn phòng."]),
        T("V", OKAY),
        T("C", ["Dạ {m} cảm ơn {y}.", "Có hóa đơn đỏ nếu {y} cần.", "Chúc {y} đi vui vẻ."], 0.6),
    ],
    "người nhận nhầm tiền trả lại qua ngân hàng": [
        T("C", ["Chào {y}, {m} hình như vừa chuyển nhầm {amt} vào tài khoản của {y}.",
                "Alo, {m} chuyển khoản nhầm một số cuối nên tiền sang tài khoản {y}.",
                "{Y} ơi cho {m} hỏi, {y} có nhận được một khoản lạ sáng nay không?"]),
        T("V", ["Để {v} kiểm tra.", "Có, {v} đang thắc mắc.", "Vậy giờ làm sao?"]),
        T("C", ["{M} đã báo ngân hàng tra soát, ngân hàng sẽ liên hệ {y} để hoàn lại.",
                "{Y} không cần chuyển cho {m} đâu, cứ ra ngân hàng làm thủ tục hoàn tiền giúp {m}.",
                "{M} làm đơn ở chi nhánh rồi, {y} chờ ngân hàng gọi nhé."]),
        T("V", ["Ừ để {v} ra ngân hàng.", "Được, {v} sẽ phối hợp."], 0.8),
        T("C", ["Cảm ơn {y} nhiều.", "Phiền {y} quá.", "May mà gặp người tốt."]),
    ],
    "mua bán đồ cũ": [
        T("C", ["Chào {y}, {m} thấy {y} đăng bán cái xe đạp, còn không ạ?",
                "Alo {y} bán cái bàn làm việc đúng không, {m} muốn hỏi giá.",
                "{M} hỏi cái điện thoại cũ {y} rao trên mạng."]),
        T("V", ["Còn em, giá {small}.", "Đúng rồi, {v} bán {amt}.", "Còn, máy dùng một năm."]),
        T("C", ["{M} qua xem trực tiếp {day} được không?", "Bớt chút được không {y}?",
                "Có hộp và sạc không {y}?"]),
        T("V", ["Được, {hour} nhé.", "Bớt cho em chút xíu.", "Đủ hết."]),
        T("C", ["Ok, xem ưng thì {m} trả tiền mặt luôn.", "Vậy mai {m} qua, chuyển khoản lúc nhận hàng nhé.",
                "Rồi, {m} qua xem rồi lấy."]),
    ],
}

# ------------------------------------------------------------------ kịch bản thêm ở đợt 6 (sau khi chuyển sang huấn luyện)
SCAM.update({
    "giả bảo trì máy lọc nước": [
        T("C", ["Chào {y}, {m} bên trung tâm bảo hành máy lọc nước, máy nhà {y} tới kỳ thay lõi miễn phí.",
                "{M} là kỹ thuật viên hãng lọc nước, hệ thống báo máy nhà {y} nhiễm khuẩn cần xử lý gấp.",
                "Trung tâm chăm sóc khách hàng thông báo máy lọc nước của {y} được tặng gói bảo trì năm năm."]),
        T("V", ["Thay lõi miễn phí thật à?", "Nhiễm khuẩn là sao?", "Nhà {v} có mua máy đó thật."]),
        T("C", ["Lõi thì miễn phí nhưng {y} đóng trước {small} phí kiểm định nước, chuyển khoản cho {m}.",
                "{Y} phải thay cả bộ lõi {amt}, chuyển trước một nửa vào tài khoản của {m} để {m} đặt hàng.",
                "Để kích hoạt gói bảo trì {y} bấm đường link {m} gửi rồi nhập số thẻ và mã ngân hàng gửi về."]),
        T("V", WARY, 0.6),
        T("C", ["Không thay trong hôm nay thì uống vào ngộ độc bên {m} không chịu trách nhiệm.",
                "Thợ đang ở gần nhà {y}, chuyển xong {m} qua liền.", "Chương trình hết hạn {deadline}."]),
    ],
    "giả cán bộ phòng cháy chữa cháy": [
        T("C", ["Tôi là cán bộ đội phòng cháy chữa cháy quận, cơ sở của {y} có tên trong danh sách kiểm tra đột xuất.",
                "Phòng cảnh sát phòng cháy thông báo cửa hàng của {y} chưa có chứng chỉ huấn luyện nghiệp vụ.",
                "Tôi gọi từ đội phòng cháy, nhà trọ của {y} thiếu hồ sơ nên sẽ bị đình chỉ hoạt động."]),
        T("V", ["Kiểm tra khi nào?", "Chứng chỉ gì vậy?", "Giờ phải làm sao?"]),
        T("C", ["{Y} đăng ký lớp tập huấn và mua bộ tài liệu {amt}, chuyển khoản cho kế toán của đội.",
                "{Y} đặt mua mười bình chữa cháy qua công ty tôi giới thiệu, chuyển cọc {amt} trong hôm nay.",
                "{Y} kết bạn {app} với cán bộ phụ trách, chuyển lệ phí cấp chứng chỉ {small} thì đoàn không xuống nữa."]),
        T("V", WARY, 0.6),
        T("C", ["Không nộp {deadline} thì mai đoàn xuống lập biên bản phạt {amt}.",
                "Tôi báo trước là để giúp {y}, {y} chuyển ngay đi.", "Việc này {y} đừng hỏi phường, họ không nắm đâu."]),
    ],
    "giả thông báo trúng tuyển": [
        T("C", ["Chào {y}, {m} bên phòng tuyển sinh, con {y} đã trúng tuyển hệ chất lượng cao của trường.",
                "{M} là cán bộ tuyển sinh đại học, em nhà mình được xét tuyển thẳng kèm học bổng.",
                "Phòng nhân sự tập đoàn xin báo {y} trúng tuyển vị trí nhân viên văn phòng lương {amt}."]),
        T("V", ["Thật không em?", "Cháu đâu có đăng ký hệ đó.", "Bao giờ nhập học?"]),
        T("C", ["Để giữ chỗ {y} chuyển {amt} tiền nhập học {deadline} vào tài khoản cán bộ thu.",
                "{Y} đóng trước {small} phí hồ sơ và đồng phục, chuyển khoản cho {m} rồi {m} gửi giấy báo.",
                "{Y} đóng {amt} tiền đặt cọc đào tạo, sau hai tháng làm việc công ty hoàn lại."]),
        T("V", ["Sao không đóng ở trường?", "Để {v} lên tận nơi hỏi đã."], 0.7),
        T("C", ["Hết hôm nay là suất chuyển cho thí sinh dự bị.", "Trường đang quá tải nên thu qua tài khoản cá nhân.",
                "{Y} chuyển trước, giấy tờ nhận sau."]),
    ],
    "giả bác sĩ bán thuốc": [
        T("C", ["Chào {y}, {m} là bác sĩ bệnh viện trung ương, {m} xem hồ sơ thấy {y} bị xương khớp lâu năm.",
                "{M} gọi từ viện y học cổ truyền, {y} có tên trong chương trình hỗ trợ điều trị tiểu đường.",
                "Tôi là dược sĩ của viện, bệnh mất ngủ của {y} có thuốc đặc trị mới nhập về."]),
        T("V", ["Đúng rồi, {v} đau lâu rồi.", "Có khỏi hẳn không?", "Thuốc gì vậy?"]),
        T("C", ["Liệu trình ba tháng {amt}, cam kết khỏi dứt điểm, {y} chuyển khoản trước để {m} gửi thuốc.",
                "Nhà nước hỗ trợ một nửa, {y} chỉ đóng {amt}, chuyển cho thủ quỹ của viện.",
                "Thuốc không bán ngoài tiệm, {y} đặt cọc {small} rồi nhận hàng trả nốt."]),
        T("V", ["Để {v} hỏi bác sĩ đang khám cho {v} đã.", "Sao không kê đơn ở bệnh viện?"], 0.7),
        T("C", ["{Y} ngưng hết thuốc tây đi, uống thuốc của {m} là đủ.", "Còn đúng mười suất hỗ trợ, {y} chuyển {deadline}.",
                "Không khỏi {m} hoàn tiền gấp đôi, {y} yên tâm chuyển đi."]),
    ],
    "giả ví trả sau": [
        T("C", ["Chào {y}, {m} bên ví điện tử, tài khoản ví trả sau của {y} được nâng hạn mức lên {amt}.",
                "{M} là nhân viên ví trả sau, {y} đang có khoản nợ {small} sắp bị tính lãi phạt.",
                "Ví điện tử thông báo {y} được hoàn {small} do thanh toán hóa đơn tháng trước."]),
        T("V", ["{V} có dùng ví trả sau đâu.", "Nâng thế nào em?", "Hoàn về đâu?"]),
        T("C", ["{Y} đọc mã xác thực vừa gửi về máy để {m} kích hoạt.",
                "Để hủy khoản nợ {y} cho {m} mật khẩu ví và mã OTP.",
                "{Y} bấm đường link {m} nhắn, đăng nhập ví rồi nhập số thẻ liên kết."]),
        T("V", WARY, 0.6),
        T("C", ["Mã hết hạn sau hai phút, {y} đọc nhanh.", "Không xử lý {deadline} là {y} bị báo nợ xấu.",
                "{Y} làm ngay, {m} đang giữ lệnh."]),
    ],
    "giả cảnh báo rò rỉ dữ liệu": [
        T("C", ["Chào {y}, {m} gọi từ trung tâm thông tin tín dụng, dữ liệu của {y} vừa bị rò rỉ sau một vụ tấn công mạng.",
                "{M} bên bộ phận an ninh {bank}, thông tin thẻ của {y} nằm trong danh sách bị lộ.",
                "Trung tâm an toàn thông tin thông báo tài khoản của {y} đang bị rao bán trên mạng."]),
        T("V", ["Trời, có sao không?", "Lộ những gì?", "Giờ phải làm gì?"]),
        T("C", ["{Y} cài ứng dụng bảo vệ {m} gửi qua {app}, cấp quyền rồi đăng nhập ngân hàng để quét.",
                "{Y} chuyển tiền sang tài khoản bảo vệ tạm thời của ngân hàng, {m} đọc số.",
                "{Y} đọc số thẻ, ngày hết hạn và mã vừa gửi về để {m} khóa khẩn cấp."]),
        T("V", WARY, 0.6),
        T("C", ["Kẻ gian đang rút tiền, {y} làm trong năm phút.", "{Y} đừng ra quầy, ra quầy là chậm mất.",
                "Chậm là mất hết, {y} làm theo {m} ngay."]),
    ],
    "giả kêu gọi từ thiện": [
        T("C", ["Chào {y}, {m} bên nhóm thiện nguyện, miền Trung đang lũ lớn, bà con thiếu lương thực.",
                "{M} là nhân viên quỹ từ thiện, có một em bé ung thư cần mổ gấp trong ba ngày tới.",
                "Nhóm tình nguyện của {m} đang quyên góp xây cầu cho trẻ em vùng cao."]),
        T("V", ["Nhóm em là nhóm nào?", "Sao không qua Chữ thập đỏ?", "Chuyển thế nào?"]),
        T("C", ["Các tổ chức lớn thủ tục lâu, {y} chuyển vào tài khoản cá nhân của {m} thì mai có hàng lên ngay.",
                "{Y} chuyển qua ví điện tử số của {m} cho nhanh, tài khoản của quỹ mất ba ngày mới về.",
                "{Y} chuyển cho trưởng nhóm, {m} gửi ảnh và danh sách sau."]),
        T("V", ["Cho {v} số bệnh viện để hỏi.", "Để {v} xem lại đã."], 0.7),
        T("C", ["Theo quy định bảo mật {m} không cho số được, {y} thương thì chuyển ngay.",
                "Chỉ còn hôm nay thôi, chậm là không kịp.", "Nhiều người chuyển năm mười triệu rồi, {y} giúp một tay."]),
    ],
    "giả nhà hàng thu cọc": [
        T("C", ["Chào {y}, {m} bên nhà hàng, {y} đặt bàn sinh nhật {day} đúng không ạ?",
                "{M} là nhân viên đặt tiệc, {m} thấy {y} nhắn hỏi bàn trên fanpage.",
                "Nhà hàng xin báo tiền cọc {y} chuyển lúc nãy chưa được hệ thống ghi nhận."]),
        T("V", ["Ừ đúng rồi.", "{V} mới hỏi thôi.", "Sao lại chưa ghi nhận?"]),
        T("C", ["Nội dung chuyển khoản thiếu mã đặt bàn, {y} chuyển lại vào tài khoản cá nhân của quản lý để {m} nhập tay.",
                "Chỉ còn một bàn, {y} cọc {amt} vào tài khoản cá nhân {m} vì tài khoản công ty phải chờ ba ngày.",
                "Voucher của {y} đang chờ kích hoạt, {y} chuyển thêm {small} phí xác thực."]),
        T("V", ["Sao lại tài khoản cá nhân?", "Sao lại có thêm phí?"], 0.8),
        T("C", ["Tài khoản công ty đang bảo trì, quá ba mươi phút là hệ thống hủy bàn.",
                "Ai cũng chuyển như vậy, {y} làm nhanh kẻo có khách khác lấy.", "Phí đó {m} hoàn lại khi {y} tới quán."]),
    ],
    "giả khách sạn hoàn tiền": [
        T("C", ["Chào {y}, {m} gọi từ khách sạn, hệ thống ghi nhận {y} đặt phòng và đã cọc {amt} qua thẻ.",
                "{M} là lễ tân khách sạn ở {city}, đặt phòng của {y} bị trừ tiền hai lần.",
                "Bộ phận đặt phòng thông báo thanh toán của {y} bị lỗi, cần xác minh lại."]),
        T("V", ["{V} có đặt gì đâu.", "Vậy hoàn lại cho {v}.", "Xác minh thế nào?"]),
        T("C", ["Vậy có người dùng thẻ của {y} rồi, {y} bấm đường link {m} gửi, nhập số thẻ và mã OTP để hủy.",
                "{Y} đọc số thẻ, ngày hết hạn và mã ngân hàng vừa gửi để {m} làm lệnh hoàn.",
                "{Y} chuyển trước {small} phí hoàn tiền liên ngân hàng, {m} chuyển lại đủ."]),
        T("V", WARY, 0.6),
        T("C", ["Không hủy trước sáu giờ là thẻ {y} bị trừ nốt phần còn lại.", "{Y} đọc mã luôn, {m} đang đứng ở quầy.",
                "Chậm là khách sạn không hoàn được nữa."]),
    ],
})

NORMAL.update({
    "bảo trì máy lọc nước thật": [
        T("C", ["Chào {y}, {m} bên trung tâm bảo hành máy lọc nước, máy nhà {y} tới kỳ thay lõi.",
                "{M} là kỹ thuật viên lọc nước, {m} gọi hẹn lịch bảo dưỡng định kỳ.",
                "Trung tâm bảo hành nhắc máy lọc nước nhà {y} dùng được sáu tháng rồi."]),
        T("V", ["Thay hết bao nhiêu?", "Bao giờ qua được?", "Có cần thay không em?"]),
        T("C", ["Lõi số một {small}, thợ qua kiểm tra, {y} đồng ý mới thay, trả tiền có hóa đơn.",
                "{Day} {m} qua, kiểm tra miễn phí.", "Nước vẫn trong thì chưa cần, {m} qua đo rồi báo {y}."]),
        T("V", OKAY),
        T("C", ["Dạ {m} cảm ơn {y}.", "Thợ sẽ gọi trước khi tới.", "{Y} không cần chuyển khoản trước gì đâu ạ."], 0.6),
    ],
    "phòng cháy chữa cháy kiểm tra thật": [
        T("C", ["Tôi là cán bộ đội phòng cháy chữa cháy quận, {day} đoàn kiểm tra định kỳ cơ sở của {y}.",
                "Ủy ban phường thông báo lớp tập huấn phòng cháy miễn phí cho các hộ kinh doanh.",
                "Đội phòng cháy gửi công văn kiểm tra, tôi gọi xác nhận {y} đã nhận chưa."]),
        T("V", ["Cần chuẩn bị gì?", "Học ở đâu?", "{V} nhận được rồi."]),
        T("C", ["{Y} chuẩn bị hồ sơ và bình chữa cháy còn hạn, đoàn làm việc tại chỗ, không thu khoản nào.",
                "Học tại hội trường phường lúc {hour}, miễn phí.", "Vậy {day} đoàn xuống, có giấy giới thiệu."]),
        T("V", OKAY),
        T("C", ["Cảm ơn {y}.", "Bình chữa cháy {y} tự mua ở cửa hàng có hóa đơn là được.", "Có gì {y} hỏi thêm ở phường."], 0.6),
    ],
    "trường báo trúng tuyển thật": [
        T("C", ["Chào {y}, {m} bên phòng tuyển sinh, con {y} có tên trong danh sách trúng tuyển đợt một.",
                "Trường đại học xin thông báo em nhà mình đủ điểm vào ngành đã đăng ký.",
                "Phòng nhân sự công ty báo {y} đã qua vòng phỏng vấn."]),
        T("V", ["Mừng quá, thủ tục sao em?", "Bao giờ nhập học?", "Khi nào đi làm?"]),
        T("C", ["Em ấy xác nhận nhập học trên cổng của bộ, học phí đóng theo mã sinh viên sau khi nhập học.",
                "Nhập học {day}, mang giấy báo và học bạ gốc lên trường.",
                "{Y} lên công ty ký hợp đồng {day}, không phải đóng khoản nào."]),
        T("V", OKAY),
        T("C", ["Chúc mừng gia đình.", "Thông tin có trên trang chính thức của trường.", "Hẹn gặp {y}."], 0.6),
    ],
    "bác sĩ và nhà thuốc thật": [
        T("C", ["Chào {y}, phòng khám gọi báo kết quả xét nghiệm của {y} đã có.",
                "{M} là dược sĩ nhà thuốc bệnh viện, thuốc của {y} tháng này về rồi.",
                "Bác sĩ nhờ {m} nhắc {y} lịch tái khám {day}."]),
        T("V", ["Kết quả sao em?", "Hết bao nhiêu?", "Mấy giờ khám?"]),
        T("C", ["Bình thường ạ, {y} lên nhận bản giấy hoặc xem trên ứng dụng bệnh viện.",
                "Có bảo hiểm nên {y} chỉ trả phần chênh lệch tại quầy.", "{Hour}, {y} mang sổ khám theo."]),
        T("V", OKAY),
        T("C", ["Dạ {m} cảm ơn {y}.", "{Y} uống thuốc theo đơn bác sĩ kê nhé.", "Chúc {y} mau khỏe."], 0.6),
    ],
    "ví điện tử thật hỗ trợ": [
        T("C", ["Chào {y}, {m} bên ví điện tử, {y} có gửi yêu cầu hỗ trợ giao dịch nạp tiền.",
                "{M} là nhân viên chăm sóc khách hàng ví điện tử, khoản hoàn tiền của {y} đã được duyệt.",
                "Ví điện tử gọi xác nhận {y} vừa liên kết ngân hàng mới."]),
        T("V", ["Đúng rồi em.", "Bao giờ nhận được?", "Ừ {v} mới liên kết."]),
        T("C", ["Tiền sẽ về ví trong hai mươi bốn giờ, {y} xem trong lịch sử giao dịch.",
                "Trong ba ngày làm việc, {y} không cần làm gì thêm.",
                "Vậy là đúng ạ, {m} chỉ gọi xác nhận, không cần {y} cung cấp mật khẩu hay mã nào."]),
        T("V", OKAY),
        T("C", ["Dạ {m} cảm ơn {y}.", "Cần hỗ trợ {y} nhắn trong mục trợ giúp của ứng dụng.", "Chúc {y} một ngày tốt lành."], 0.6),
    ],
    "ngân hàng thật báo đổi thẻ": [
        T("C", ["Chào {y}, {m} gọi từ {bank}, ngân hàng phát hành lại thẻ cho khách hàng sau đợt nâng cấp bảo mật.",
                "{M} bên {bank}, thẻ của {y} sắp hết hạn, thẻ mới đã về chi nhánh.",
                "Ngân hàng {bank} khuyến nghị {y} đổi mật khẩu định kỳ."]),
        T("V", ["Đổi thế nào?", "Nhận ở đâu?", "Có sao không em?"]),
        T("C", ["{Y} mang căn cước ra chi nhánh đổi thẻ, miễn phí.", "{Y} ghé chi nhánh đã mở thẻ, giờ hành chính.",
                "Không sao ạ, {y} tự đổi trong ứng dụng, đừng cho ai biết mật khẩu."]),
        T("V", OKAY),
        T("C", ["Dạ {m} cảm ơn {y}.", "Ngân hàng không hỏi số thẻ hay mã OTP qua điện thoại đâu ạ.", "Có gì {y} gọi tổng đài in sau thẻ."], 0.6),
    ],
    "quyên góp qua tổ chức chính thức": [
        T("C", ["Chào {y}, tôi là tổ trưởng dân phố, phường phát động ủng hộ đồng bào bão lụt.",
                "Công đoàn công ty thông báo đợt quyên góp ủng hộ miền Trung.",
                "Hội chữ thập đỏ phường gọi mời {y} tham gia hiến máu {day}."]),
        T("V", ["Đóng ở đâu?", "Mỗi người bao nhiêu?", "Hiến ở đâu?"]),
        T("C", ["Ai ủng hộ thì nộp tại nhà văn hóa, có ký sổ và biên nhận của Mặt trận.",
                "Tùy tâm, công đoàn trừ vào lương theo danh sách ký tên rồi nộp cho Mặt trận.",
                "Tại trạm y tế phường lúc {hour}, hoàn toàn tự nguyện."]),
        T("V", OKAY),
        T("C", ["Cảm ơn {y}.", "Danh sách sẽ được dán công khai ở bảng tin.", "Không ai gọi điện thu tiền riêng đâu, {y} lưu ý nhé."], 0.6),
    ],
    "nhà hàng thật xác nhận đặt bàn": [
        T("C", ["Chào {y}, {m} bên nhà hàng, {m} gọi xác nhận {y} đặt bàn {day} lúc {hour}.",
                "{M} là nhân viên đặt tiệc, {y} muốn đặt tiệc sinh nhật bên {m} đúng không ạ?",
                "Nhà hàng xin xác nhận bàn mười người của {y} tối nay."]),
        T("V", ["Đúng rồi em.", "Ừ, có cần cọc không?", "Giữ bàn tới mấy giờ?"]),
        T("C", ["Bên {m} giữ bàn mười lăm phút, không cần đặt cọc.",
                "Tiệc lớn thì cọc ba mươi phần trăm tại quầy hoặc vào tài khoản công ty in trên phiếu đặt tiệc.",
                "Bên {m} giữ tới bảy rưỡi, {y} tới trễ thì gọi báo giúp."]),
        T("V", OKAY),
        T("C", ["Dạ {m} cảm ơn {y}.", "Hủy trước một ngày bên {m} hoàn cọc đầy đủ.", "Hẹn gặp {y}."], 0.6),
    ],
    "khách sạn thật xác nhận đặt phòng": [
        T("C", ["Chào {y}, {m} gọi từ khách sạn ở {city}, xác nhận {y} đặt phòng đôi hai đêm.",
                "{M} là lễ tân khách sạn, phòng {y} đặt qua ứng dụng đã được giữ.",
                "Khách sạn xin hỏi giờ {y} dự kiến nhận phòng {day}."]),
        T("V", ["Đúng rồi em.", "Thanh toán thế nào?", "Khoảng {hour} {v} tới."]),
        T("C", ["Dạ {y} thanh toán khi nhận phòng, bên {m} chỉ cần căn cước lúc làm thủ tục.",
                "{Y} đã trả trên ứng dụng rồi nên không cần thanh toán thêm.",
                "Dạ nhận phòng từ hai giờ chiều, tới sớm {y} gửi hành lý ở quầy."]),
        T("V", OKAY),
        T("C", ["Dạ {m} cảm ơn {y}.", "Hủy trước một ngày không mất phí ạ.", "Chúc {y} chuyến đi vui vẻ."], 0.6),
    ],
})

# Kịch bản dành riêng cho tập validation (không có dòng nào trong tập train).
VALIDATION_FAMILIES = {
    "giả tòa án báo nợ thẻ", "giả đổi sim 5G", "giả cảnh báo rò rỉ dữ liệu", "giả khách sạn hoàn tiền",
    "tòa án xác nhận người làm chứng", "nhà mạng mời đổi sim tại cửa hàng", "ngân hàng thật báo đổi thẻ",
    "khách sạn thật xác nhận đặt phòng",
}


def generate() -> list[dict]:
    """Sinh ``PER_FAMILY`` biến thể cho mỗi kịch bản; cuộc bình thường đi theo một mạch chuyện để hỏi đáp khớp nhau."""
    rng = random.Random(SEED)
    generic = set(WARY + OKAY)
    rows = []
    for label, families in ((1, SCAM), (0, NORMAL)):
        for family, script in families.items():
            seen: set[str] = set()
            attempts = 0
            while len(seen) < PER_FAMILY and attempts < PER_FAMILY * 80:
                attempts += 1
                me, you, victim = rng.choice(PRONOUNS)
                values = {key: rng.choice(options) for key, options in FILLERS.items()} | {"m": me, "y": you, "v": victim}
                style = rng.choice(SPEAKER_STYLES)
                names = {"C": style[0], "V": style[1], "C2": style[2]}
                thread = rng.randrange(3)
                follow_thread = label == 0 or rng.random() < 0.5
                turns = []
                for speaker, options, keep in script:
                    if rng.random() >= keep:
                        continue
                    shared = any(option in generic for option in options)
                    chosen = options[thread % len(options)] if follow_thread and not shared else rng.choice(options)
                    turns.append([names[speaker], _fill(chosen, values)])
                key = " ".join(text for _, text in turns)
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"id": f"gm-{len(rows):04}", "label": label, "family": family, "turns": turns,
                             "split": "validation" if family in VALIDATION_FAMILIES else "train"})
    return rows


def main() -> int:
    """Sinh các hội thoại bổ sung và ghi ra file."""
    rows = generate()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8"))
    scams = sum(row["label"] for row in rows)
    held = sum(1 for row in rows if row["split"] == "validation")
    print(f"wrote {OUT}: {len(rows)} conversations ({scams} scam, {len(rows) - scams} normal), "
          f"{len(SCAM)} scam families, {len(NORMAL)} normal families, {held} reserved for validation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
