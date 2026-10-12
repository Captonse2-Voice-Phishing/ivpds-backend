"""Dựng bộ test "đoạn ngắn một người nói": chỉ có lời người gọi, khoảng 10 giây, không có người nghe đáp lại.

Cách dùng (chạy từ thư mục ``ai``):

    python -m tools.short_monologues_build

Ghi ``data/extra_tests/short_monologues.jsonl``. Bộ này sinh ra từ một phản hồi thực tế (12/10/2026): người dùng ghi
âm một đoạn ngắn chỉ có tiếng người gọi nhờ đặt cọc, nhắc đóng phí... và hệ thống báo mức cao. Bộ gồm hai nửa:

* lời đề nghị thanh toán, nhắc phí, mượn tiền trong đời thường (nhãn bình thường);
* lời lừa đảo cũng ngắn và cũng một chiều (nhãn lừa đảo), để việc sửa báo nhầm không làm sót lừa đảo.

Mọi câu ở đây viết tay từng câu (``synthetic = true``) và **chỉ dùng để test, không bao giờ đưa vào huấn luyện**;
các kịch bản huấn luyện cùng chủ đề nằm ở ``tools/dataset_synthesize_vi_short.py`` và dùng câu chữ khác.
"""

import json
import sys
from pathlib import Path

OUT = Path("data/extra_tests/short_monologues.jsonl")

NORMAL = {
    "đặt cọc, giữ chỗ": [
        "Dạ em chào anh, em gọi từ khách sạn Hoa Mai ạ. Anh đặt phòng ngày hai mươi tháng này, anh vui lòng chuyển khoản đặt cọc năm trăm nghìn để bên em giữ phòng cho anh nhé.",
        "Chào chị, em bên cửa hàng điện máy. Cái tủ lạnh chị hỏi hôm qua còn đúng một cái, chị đặt cọc trước ba trăm nghìn thì em giữ hàng cho chị đến cuối tuần.",
        "Em chào anh chị, em ở trung tâm tiệc cưới. Ngày mười hai tháng sau sảnh lớn còn trống, anh chị muốn giữ ngày thì qua ký hợp đồng và đặt cọc hai mươi phần trăm giúp em.",
        "Alo anh ơi, em bên nhà xe. Anh đặt hai ghế đi Đà Lạt tối thứ sáu, anh chuyển khoản trước tiền vé theo số tài khoản in trên trang của nhà xe để em xuất vé nhé.",
        "Chị ơi em ở tiệm áo cưới. Bộ váy chị thử hôm chủ nhật em đang giữ, chị cọc một triệu thì em không cho khách khác thuê ngày đó nữa ạ.",
        "Dạ chào anh, homestay bên em xác nhận anh đặt hai đêm cuối tuần. Bên em nhận cọc một nửa, anh chuyển khoản hay tới nơi thanh toán đều được, anh báo em nhé.",
        "Chào anh, em gọi từ showroom xe máy. Mẫu xe anh xem về hàng rồi, anh muốn lấy màu đen thì ghé cửa hàng đặt cọc hai triệu, bên em có viết phiếu thu.",
        "Em chào chị, em bên studio chụp ảnh. Lịch chụp gia đình ngày mùng ba em đã xếp, chị chuyển trước ba trăm nghìn tiền cọc để em chốt lịch với thợ ạ.",
    ],
    "nhắc đóng phí, học phí, hóa đơn": [
        "Chào phụ huynh, em là giáo vụ của trường. Em xin nhắc gia đình đóng học phí học kỳ một cho cháu trong tuần này ạ, hạn cuối là thứ sáu.",
        "Chào anh, em là nhân viên công ty bảo hiểm. Hợp đồng của anh sắp đến hạn đóng phí năm nay, anh nhớ đóng trước ngày ba mươi để hợp đồng không bị gián đoạn nhé.",
        "Chị ơi em ở ban quản lý chung cư. Phí quản lý quý này chị chưa đóng, chị đóng ở quầy lễ tân hoặc chuyển khoản theo thông báo dán ở thang máy giúp em.",
        "Dạ em gọi từ trung tâm tiếng Anh. Khóa của bé sắp hết, nếu gia đình cho bé học tiếp thì đóng học phí khóa mới trước ngày mười lăm để bên em xếp lớp ạ.",
        "Anh ơi em bên phòng tập. Thẻ tập của anh còn năm ngày nữa hết hạn, anh gia hạn tại quầy trước cuối tháng thì được tặng thêm một tháng.",
        "Chào chị, em gọi từ nhà mạng. Cước internet tháng này của nhà mình là hai trăm hai mươi nghìn, chị thanh toán trên ứng dụng hoặc ra cửa hàng trước ngày hai mươi lăm giúp em.",
        "Cô ơi cháu là thủ quỹ hội phụ huynh lớp bốn A. Quỹ lớp học kỳ này mỗi nhà ba trăm nghìn, cô gửi cháu lúc đón con hoặc chuyển khoản cũng được ạ.",
        "Dạ em ở nha khoa. Đợt niềng răng của chị đến kỳ thanh toán thứ hai rồi, lần tái khám tới chị mang theo để đóng tại quầy giúp em nhé.",
    ],
    "người quen mượn tiền, nhờ trả hộ": [
        "Ê Tuấn ơi, tao đang kẹt quá, mày cho tao mượn hai triệu được không. Cuối tháng có lương tao trả, mày chuyển vào số tài khoản cũ của tao nha.",
        "Mẹ ơi con đây, tháng này con đóng tiền trọ với tiền học thêm hơi nhiều. Mẹ gửi cho con thêm một triệu vào tài khoản của con như mọi lần được không mẹ.",
        "Chị Lan ơi em Hoa đây. Hôm qua đi ăn chị trả hộ em hai trăm rưỡi, chị gửi em số tài khoản em chuyển lại cho chị nhé.",
        "Anh ơi tối qua liên hoan phòng hết bốn triệu tám, chia ra mỗi người ba trăm hai. Anh chuyển cho em khi nào tiện, em ứng trước rồi.",
        "Bố ơi con Minh đây. Xe con hỏng giữa đường, sửa hết tám trăm mà con không mang đủ tiền, bố chuyển cho con vào tài khoản của con nhé, tối con về con kể.",
        "Dì ơi cháu Ngân nè. Mẹ cháu dặn cháu gọi nhắc dì khoản tiền hụi tháng này, dì gửi mẹ cháu trước chủ nhật là được ạ.",
        "Ông Hùng ơi tôi Bình đây. Tiền góp mua quà cưới cho thằng Dũng mỗi người năm trăm, ông chuyển khoản hay mai lên công ty đưa tôi cũng được.",
    ],
    "giao hàng, dịch vụ, sửa chữa báo tiền": [
        "Alo chị ơi em giao hàng đây, chị có đơn đôi giày hết bốn trăm năm mươi nghìn thu hộ. Em đang ở dưới sảnh, chị xuống nhận hay em gửi bảo vệ ạ.",
        "Anh ơi em ở tiệm sửa xe. Xe anh em kiểm tra rồi, phải thay nhông xích với má phanh, tổng hết chín trăm nghìn, anh đồng ý thì em làm luôn chiều anh qua lấy.",
        "Chào chị, em thợ điện lạnh hôm qua qua nhà mình. Máy lạnh thay tụ với nạp ga hết sáu trăm, chị chuyển khoản cho em theo số ghi trên phiếu bảo hành cũng được.",
        "Dạ chào anh, phòng khám gọi xác nhận lịch khám tổng quát sáng thứ bảy. Chi phí gói khám là một triệu hai, anh thanh toán tại quầy khi đến ạ.",
        "Chị ơi em bên tiệm hoa. Lẵng hoa khai trương chị đặt là tám trăm nghìn, sáng mai em giao, chị thanh toán khi nhận hoặc chuyển khoản trước đều được.",
        "Anh ơi em chủ nhà đây. Tháng này tiền phòng ba triệu rưỡi, điện nước hết bốn trăm hai, anh chuyển khoản cho em như mọi tháng nhé.",
        "Em chào chị, em bên công ty du lịch. Tour Phú Quốc của gia đình mình đã có vé máy bay, chị thanh toán nốt phần còn lại tại văn phòng trước ngày khởi hành một tuần giúp em.",
        "Chào anh, em gọi từ ngân hàng theo lịch nhắc nợ. Kỳ trả góp tháng này của anh là ngày mười lăm, anh nộp tiền vào tài khoản của chính anh trên ứng dụng như các kỳ trước là được ạ.",
    ],
    "mua bán, chốt đơn": [
        "Chào chị, em bên shop quần áo trên mạng. Đơn hai cái váy của chị hết năm trăm chín mươi nghìn, chị muốn chuyển khoản trước hay nhận hàng rồi trả tiền ạ.",
        "Anh ơi em bán cái laptop anh hỏi trên chợ mạng. Giá chốt mười hai triệu, anh qua xem máy, ưng thì mình giao tiền trực tiếp luôn.",
        "Dạ em gọi từ nhà sách. Bộ sách giáo khoa lớp sáu chị đặt đã về, tổng ba trăm tám mươi nghìn, chị ghé lấy và thanh toán tại quầy giúp em.",
        "Chú ơi cháu bên cửa hàng vật liệu. Xe cát với hai mươi bao xi măng chú đặt sáng mai giao, tổng bốn triệu sáu, chú trả tiền cho tài xế khi nhận hàng nhé.",
        "Chị ơi em là người mua cái tủ chị rao bán. Em lấy nhé, chiều em qua chở và trả tiền mặt cho chị, chị cho em xin địa chỉ.",
    ],
}

SCAM = {
    "đòi chuyển tiền kèm đe dọa hoặc thúc ép": [
        "Tôi gọi từ cơ quan điều tra, anh đang liên quan một đường dây rửa tiền. Anh chuyển toàn bộ tiền sang tài khoản tạm giữ ngay bây giờ và không được nói với ai.",
        "Em gọi từ điện lực, nhà mình còn nợ tiền điện hai tháng. Trong ba mươi phút nữa chị không chuyển khoản vào số tài khoản em đọc thì bên em cắt điện.",
        "Con trai anh chị vừa bị tai nạn đang cấp cứu, cần đóng viện phí ngay mới mổ được. Anh chị chuyển gấp hai mươi triệu vào tài khoản bác sĩ, đừng tắt máy.",
        "Mày ơi tao đây, tao đổi số rồi. Tao đang cần gấp mười triệu, mày chuyển vào tài khoản đứa em tao nhé, đừng gọi số cũ, tao đang họp không nghe được.",
        "Đây là tòa án, anh có khoản nợ thẻ tín dụng bốn mươi triệu quá hạn. Hôm nay anh không nộp vào tài khoản thi hành án thì sẽ bị cưỡng chế.",
        "Em bên công ty tài chính, hồ sơ vay của chị được duyệt rồi. Chị chuyển trước hai triệu phí bảo hiểm khoản vay thì tiền mới giải ngân về tài khoản.",
        "Chúc mừng anh trúng xe máy trong chương trình tri ân. Anh chuyển năm trăm nghìn phí hồ sơ và thuế trước mười hai giờ trưa nay để nhận thưởng.",
        "Chị được nhận vào làm cộng tác viên chốt đơn. Chị nạp ba trăm nghìn làm nhiệm vụ đầu, hoàn thành là rút về cả gốc lẫn hoa hồng ngay.",
        "Em ở trường của bé, bé bị ngã chấn thương đầu đang chuyển lên tuyến trên. Phụ huynh chuyển ngay mười lăm triệu tạm ứng viện phí vào tài khoản em đọc đây.",
    ],
    "đòi mã OTP, thông tin thẻ, mật khẩu": [
        "Em gọi từ ngân hàng, tài khoản của anh vừa có giao dịch lạ. Anh đọc giúp em mã OTP vừa gửi về máy để em hủy giao dịch ngay.",
        "Em bên khách sạn, đặt phòng của chị bị lỗi thanh toán. Chị đọc số thẻ, ngày hết hạn và ba số mặt sau để em giữ phòng lại cho chị.",
        "Em bên công ty bảo hiểm, anh được hoàn phí ba triệu. Anh đọc số tài khoản và mã xác nhận gửi về điện thoại để em chuyển tiền hoàn.",
        "Em là shipper, đơn hàng của chị bị giữ ở kho. Chị bấm vào đường link em nhắn rồi nhập số thẻ ngân hàng để đóng phí lưu kho mới giao được.",
        "Em ở nhà mạng, thuê bao của anh sắp bị khóa hai chiều. Anh đọc mã em vừa gửi để em chuẩn hóa thông tin giữ số cho anh.",
        "Em bên ví điện tử, tài khoản của chị đang bị đăng nhập ở thiết bị lạ. Chị đọc mật khẩu và mã xác thực để em khóa lại giúp chị ngay.",
        "Tôi là cán bộ thuế, anh được hoàn thuế thu nhập cá nhân. Anh cài ứng dụng theo đường link tôi gửi rồi đăng nhập tài khoản ngân hàng để nhận tiền.",
        "Em là nhân viên ngân hàng, thẻ tín dụng của chị được nâng hạn mức. Chị đọc số thẻ và mã OTP để em kích hoạt hạn mức mới luôn.",
    ],
    "giả danh, yêu cầu cài ứng dụng hoặc giữ bí mật": [
        "Tôi là công an phường, căn cước của chị cần định danh mức hai gấp. Chị cài ứng dụng dịch vụ công theo đường link tôi gửi và làm theo hướng dẫn.",
        "Viện kiểm sát đang thụ lý hồ sơ của anh. Đây là việc mật, anh ra chỗ vắng người, không cúp máy và kê khai toàn bộ số dư các tài khoản.",
        "Em hỗ trợ kỹ thuật của ngân hàng, máy anh đang nhiễm mã độc. Anh cài phần mềm điều khiển từ xa để em xử lý, trong lúc đó anh đừng thoát ứng dụng ngân hàng.",
        "Em gọi từ sàn đầu tư, tài khoản của chị đang lãi ba mươi phần trăm. Chị nạp thêm năm mươi triệu ngay hôm nay để lên hạng VIP mới rút được tiền.",
        "Tôi là trưởng công an quận, anh không được kể chuyện này với người nhà. Anh chuyển tiền vào tài khoản an toàn của bộ để chứng minh trong sạch.",
        "Em bên chứng khoán quốc tế, chị được chọn vào nhóm kín có chuyên gia đọc lệnh. Chị chuyển tiền vào tài khoản cá nhân của trưởng nhóm để giữ suất.",
    ],
}


def main() -> int:
    """Ghi bộ test ra file JSONL, mỗi dòng một đoạn."""
    rows = []
    for label, prefix, groups in ((0, "n", NORMAL), (1, "s", SCAM)):
        number = 0
        for group, texts in groups.items():
            for text in texts:
                number += 1
                kind = "bình thường" if label == 0 else "lừa đảo"
                rows.append({"id": f"sm-{prefix}{number:02d}", "label": label,
                             "group": f"đoạn ngắn một người nói - {group} ({kind})", "text": text, "synthetic": True})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n").encode("utf-8"))
    print(f"wrote {OUT}: {len(rows)} rows ({sum(1 for r in rows if r['label'] == 0)} normal, "
          f"{sum(1 for r in rows if r['label'] == 1)} scam)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
