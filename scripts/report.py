"""Create an offline interactive preview and a data-grounded Vietnamese case study."""
import csv,json,sqlite3
from pathlib import Path
from collections import defaultdict,Counter
ROOT=Path(__file__).resolve().parents[1]

def main():
    con=sqlite3.connect(ROOT/'data/analytics.sqlite');con.row_factory=sqlite3.Row
    cube={};details=[]
    for r in con.execute('SELECT * FROM v_transactions ORDER BY Timestamp,TransactionID'):
        key=(r['Date'][:7],r['Channel'])
        if key not in cube:
            cube[key]=dict(month=key[0],channel=key[1],attempts=0,errors=0,positive=0,negative=0,net=0,mentions=0,multierror=0,technical=0,
                review=0,high=0,states=0,burst=0,clients=set(),cards=set(),groups=Counter(),bands=Counter(),ages=Counter(),primary=Counter(),errorTypes=Counter())
        a=cube[key];a['attempts']+=1;a['errors']+=r['HasError'];a['mentions']+=r['ErrorCount'];a['multierror']+=r['ErrorCount']>1
        a['technical']+='Technical Glitch' in (r['Errors'] or '');a['review']+=r['ReviewFlag'];a['high']+=r['HighValueFlag'];a['states']+=r['MultiStateFlag'];a['burst']+=r['ErrorBurstFlag']
        a['clients'].add(r['ClientID']);a['cards'].add(r['CardID'])
        if not r['HasError']:
            a['net']+=r['AmountCents']
            if r['AmountCents']>0:
                a['positive']+=r['AmountCents']
                for dest,col in [('groups','MerchantGroup'),('bands','CreditBand'),('ages','AgeBand')]:a[dest][r[col]]+=r['AmountCents']
            elif r['AmountCents']<0:a['negative']+=r['AmountCents']
        else:
            a['primary'][r['PrimaryError']]+=1
            for e in r['Errors'].split('; '):a['errorTypes'][e]+=1
        if r['ReviewFlag']:details.append({k:r[k] for k in ['TransactionID','Date','Timestamp','CardID','Amount','Channel','MerchantState','ReviewReason']})
    for a in cube.values():
        a['clients']=sorted(a['clients']);a['cards']=sorted(a['cards'])
    cards=[dict(r) for r in con.execute('SELECT CardType,Brand,SnapshotStatus,COUNT(*) N FROM DimCard GROUP BY 1,2,3')]
    m=json.loads((ROOT/'reports/metrics.json').read_text())
    payload={'cube':list(cube.values()),'details':list(reversed(details)),'cards':cards,'metrics':m}
    template=(ROOT/'assets/preview_template.html').read_text(encoding='utf-8')
    (ROOT/'reports/dashboard_preview.html').write_text(template.replace('__DATA__',json.dumps(payload,ensure_ascii=False).replace('</','<\\/')),encoding='utf-8')
    money=lambda cents:f'${cents/100:,.2f}'
    rate=lambda x,y:f'{100*x/y:.2f}%'
    channels=[dict(r) for r in con.execute('SELECT Channel,COUNT(*) N,SUM(HasError) E FROM FactTransaction GROUP BY Channel')]
    errors=[dict(r) for r in con.execute('SELECT Error,COUNT(*) N FROM FactError GROUP BY Error ORDER BY N DESC')]
    top=[dict(r) for r in con.execute('SELECT Description,SUM(AmountCents) Cents FROM v_transactions WHERE HasError=0 AND AmountCents>0 GROUP BY Description ORDER BY Cents DESC LIMIT 5')]
    compare=[dict(r) for r in con.execute("SELECT substr(Date,1,4) Y,SUM(CASE WHEN HasError=0 AND AmountCents>0 THEN AmountCents ELSE 0 END) Cents,COUNT(*) N FROM FactTransaction WHERE substr(Date,6,2)<='10' AND substr(Date,1,4) IN ('2023','2024') GROUP BY 1 ORDER BY 1")]
    change=100*(compare[1]['Cents']/compare[0]['Cents']-1)
    overlap=m['high_value']+m['multi_state']+m['error_burst']-m['review_attempts']
    case=f'''# Banking Customer & Transaction Intelligence

## Tóm tắt cho người ra quyết định

Phân tích {m['attempts']:,} bản ghi giao dịch từ {m['start']} đến {m['end']}, kết hợp {m['customer_count']:,} khách hàng, {m['card_count']:,} thẻ và 109 MCC. Đây là dữ liệu được người dùng xuất từ Xóm Data để thực hành portfolio, không phải kết quả vận hành do người thực hiện triển khai tại ngân hàng. Chưa xác minh dữ liệu là thực hay mô phỏng và chưa xác minh quyền tái phân phối.

Giá trị dương trên các dòng không ghi nhận lỗi đạt **{money(m['positive_cents'])}**; giá trị ròng tương ứng **{money(m['net_cents'])}**. Có **{m['error_attempts']:,}** giao dịch ghi nhận lỗi, tương đương **{rate(m['error_attempts'],m['attempts'])}**. Chỉ **{m['active_customers']}** khách hàng và **{m['active_cards']}** thẻ được quan sát trong file giao dịch. Vì vậy phạm vi giao dịch của bản xuất cần được xác nhận trước khi suy rộng cho toàn danh mục.

## 1. Câu hỏi nghiệp vụ và định nghĩa

- Head of Cards: Giá trị và số lượng giao dịch biến động ra sao, kênh nào đóng góp nhiều nhất?
- Payment Operations: Kênh và nhóm lỗi nào cần ưu tiên điều tra?
- Retail Banking: Danh mục thẻ có mức độ bao phủ quan sát như thế nào?
- Risk Operations: Quy tắc mô tả nào giúp lập danh sách kiểm tra có thể giải thích được?

Mỗi dòng fact là một bản ghi giao dịch, định danh bằng TransactionID; chưa có bằng chứng rằng các lần thử lại đã được nhóm thành một giao dịch kinh tế duy nhất. Amount âm được xem là refund-like theo mô tả nguồn, chưa liên kết được với giao dịch gốc. Blank errors chỉ có nghĩa là không ghi nhận lỗi trong file. Tiền tệ USD là giả định từ bối cảnh Mỹ vì không có cột currency. Positive volume có cả Money Transfer, không đồng nghĩa với doanh thu hay mua hàng bán lẻ.

## 2. Kiểm tra dữ liệu

Không phát hiện khóa chính trùng, khóa ngoại mồ côi, sai chủ thẻ hay nhân dòng sau JOIN. Số dư ròng được đối soát bằng số nguyên cent, tránh sai khác số thực. Các tổng theo tháng đối chiếu khớp với tổng toàn bộ.

Có {m['missing_state']:,} dòng thiếu state và {m['missing_zip']:,} dòng thiếu zip. Không loại bỏ những dòng này khỏi mẫu số tỷ lệ lỗi; nhóm địa điểm thiếu được giữ rõ ràng. Các quy tắc đa bang chỉ dùng bang Mỹ được nhận diện và merchant city khác ONLINE. Snapshot age và credit score không có lịch sử hiệu lực nên không diễn giải là giá trị tại thời điểm giao dịch.

## 3. Khối lượng và diễn biến giao dịch

| Chỉ tiêu | Kết quả toàn bộ bản xuất |
|---|---:|
| Số bản ghi | {m['attempts']:,} |
| Positive volume, không ghi nhận lỗi | {money(m['positive_cents'])} |
| Negative volume, không ghi nhận lỗi | {money(m['negative_cents'])} |
| Net volume, không ghi nhận lỗi | {money(m['net_cents'])} |
| Tổng amount trên mọi dòng, gồm lỗi | {money(m['all_recorded_cents'])} |
| Dòng amount âm / bằng 0 | {m['negative_attempts']:,} / {m['zero_attempts']:,} |

So cùng kỳ tháng 1–10, positive volume năm 2023 là {money(compare[0]['Cents'])}, năm 2024 là {money(compare[1]['Cents'])}, thay đổi **{change:+.3f}%**. Đây là mô tả mức biến động trong dữ liệu quan sát, không chứng minh tác động của chiến dịch hay thay đổi sản phẩm. Không so cả năm 2023 với 10 tháng năm 2024 rồi kết luận suy giảm.

Top 5 nhóm MCC chi tiết theo positive volume:

| MCC description | Positive volume |
|---|---:|
'''+''.join(f"| {r['Description']} | {money(r['Cents'])} |\n" for r in top)+f'''
## 4. Hiệu suất thanh toán

| Kênh | Số bản ghi | Có lỗi | Tỷ lệ lỗi |
|---|---:|---:|---:|
'''+''.join(f"| {r['Channel']} | {r['N']:,} | {r['E']:,} | {rate(r['E'],r['N'])} |\n" for r in channels)+f'''
Online có tỷ lệ lỗi quan sát cao nhất. Đây là mối liên hệ mô tả; chưa điều chỉnh sự khác biệt về merchant, số tiền, khách hàng và cơ chế xác thực. Không kết luận bản thân kênh online gây lỗi. Bước tiếp theo là đối chiếu log gateway và phân tầng theo MCC, merchant và thời gian trước khi thay đổi luồng xác thực.

| Loại lỗi | Số lần đề cập |
|---|---:|
'''+''.join(f"| {r['Error']} | {r['N']:,} |\n" for r in errors)+f'''
Có {m['error_mentions']:,} lượt đề cập lỗi trên {m['error_attempts']:,} bản ghi bị lỗi, gồm {m['multi_error_attempts']} bản ghi nhiều lỗi. Insufficient Balance chiếm {rate(errors[0]['N'],m['error_attempts'])} số bản ghi có lỗi (mỗi token xuất hiện tối đa một lần trên bản ghi trong bản xuất này). Biểu đồ Primary error gán lỗi đầu tiên để đếm mỗi bản ghi đúng một lần; thứ tự token không khẳng định nguyên nhân gốc.

Ưu tiên kiểm tra cơ chế thông báo số dư và luồng thử lại ở các giao dịch thiếu số dư. Chỉ đo hiệu quả sau can thiệp bằng định nghĩa retry/session được thống nhất, nhóm đối chứng phù hợp và tỷ lệ lỗi có cùng mẫu số; bộ dữ liệu hiện tại chưa chứng minh mức cải thiện nào.

## 5. Danh mục thẻ và độ bao phủ

**{m['active_cards']:,}/{m['card_count']:,} thẻ ({rate(m['active_cards'],m['card_count'])})** được thấy ít nhất một lần; **{m['card_count']-m['active_cards']:,}** thẻ không có bản ghi trong khoảng xuất. **{m['last30_active_cards']:,}** thẻ được thấy trong 30 ngày cuối, tính cả ngày 2024-10-31 (cửa sổ 2024-10-02 đến 2024-10-31).

Khoảng trống bao phủ lớn có thể do giới hạn bản xuất, bộ lọc hoặc hoạt động thực tế; dữ liệu chưa cho phép phân biệt. Không báo cáo 5.250 thẻ là thẻ ngủ đông. Cần xác nhận đầy đủ lịch sử giao dịch và trạng thái đóng/mở thẻ. Snapshot card counts không thay đổi theo bộ lọc năm/kênh; observed counts thay đổi theo giao dịch được chọn. Không dùng expires hiện tại để loại giao dịch lịch sử vì có thể đã gia hạn hoặc thay thẻ.

## 6. Quy tắc rà soát có thể giải thích

| Quy tắc | Bản ghi được gắn cờ | Cách hiểu |
|---|---:|---|
| Amount > MCC P99 | {m['high_value']:,} | Chỉ dòng amount dương, không lỗi; MCC có ≥30 dòng đủ điều kiện |
| Nhiều bang trong ngày theo thẻ | {m['multi_state']:,} | ≥2 bang Mỹ trong cùng ngày lịch; chỉ địa điểm vật lý |
| Chuỗi ≥3 lỗi trong 60 phút | {m['error_burst']:,} | Gắn cờ lỗi thứ ba trở đi trong cửa sổ trượt, gồm đúng mốc 60 phút |
| Hợp của ba quy tắc | {m['review_attempts']:,} | {rate(m['review_attempts'],m['attempts'])} tổng số bản ghi |

Có {overlap} bản ghi trùng giữa các quy tắc nên không cộng số cờ để lấy tổng số bản ghi. Không có chuỗi lỗi đạt ngưỡng trong bản xuất này; kết quả 0 được giữ nguyên. Quy tắc nhiều bang có thể phản ánh di chuyển hợp lệ hoặc vị trí merchant đăng ký. Chưa có nhãn gian lận để đo precision/recall, cũng không được gọi toàn bộ giá trị gắn cờ là thiệt hại gian lận.

P99 được ước tính trên toàn bộ bản xuất và đóng băng để mô tả dữ liệu. Đây không phải kiểm thử dự báo: nếu triển khai cho giao dịch tương lai cần ước lượng threshold từ quá khứ, chia thời gian, thu thập nhãn kiểm tra và đánh giá false positives, tải công việc cùng drift. Không đưa ngưỡng này vào quyết định tự động khóa thẻ.

## 7. Đề xuất hành động và cách đo

| Ưu tiên | Hành động đề xuất | Chủ trì giả định | Bằng chứng cần bổ sung | Cách đo sau triển khai |
|---|---|---|---|---|
| P0 | Xác nhận phạm vi export và độ bao phủ | Data Engineering | Điều kiện lọc, lịch sử đầy đủ, thời điểm snapshot | Reconcile số dòng, khách hàng, thẻ theo kỳ |
| P1 | Điều tra lỗi online theo merchant và MCC | Payment Operations | Log gateway, mã phản hồi, session/retry | Error rate và retry recovery với cùng mẫu số |
| P1 | Rà soát nhóm thiếu số dư | Cards Product | Số dư tại thời điểm thử, lịch sử thử lại | Nhóm đối chứng và tỷ lệ khôi phục thanh toán |
| P2 | Thẩm định quy tắc rà soát | Risk Operations | Nhãn reviewed/legitimate/fraud | Precision, thời gian xử lý, số cảnh báo/ngày |
| P2 | Kiểm tra thẻ không có quan sát trước chiến dịch | Retail Banking | Trạng thái thẻ và toàn bộ giao dịch | Mức bao phủ trước; activation lift sau thử nghiệm |

Đây là đề xuất dựa trên mô tả dữ liệu, chưa có tác động kinh doanh đã thực hiện.

## 8. Bằng chứng kỹ thuật và giới hạn nghiệm thu

Pipeline chuẩn thư viện Python, số tiền gốc được chuyển sang integer cents; SQLite phục vụ JOIN, CTE, LAG, ROW_NUMBER và SUM OVER. Mô hình Power BI gồm DimCustomer → DimCard → FactTransaction, DimDate và DimMCC lọc fact, FactError tách token lỗi, DimRule rời để trình bày các cờ. Có {len(__import__('build_powerbi').MEASURES)} DAX measures và 4 trang PBIR được sinh bằng code.

Đã chạy pipeline, 26 truy vấn SQL và kiểm tra đối soát dữ liệu trong môi trường tạo file. Các kiểm tra cấu trúc và schema bổ sung được ghi tại reports/validation.json và reports/schema_validation.json nếu có. Bản HTML là preview phân tích offline, không phải ảnh chụp Power BI. Chưa có Power BI Desktop Windows tại môi trường tạo file nên chưa thực thi DAX/M, chưa xác nhận native visuals render và chưa tạo PBIX. Người dùng đang dùng Desktop June 2026 2.155.756.0; xem docs/HUONG_DAN_VI.md để mở, refresh và nghiệm thu.

## 9. Nguồn tham khảo

- Xóm Data Banking schema: https://dataset.xomdata.com/datasets/schema/banking
- Ý tưởng code-first PBIR tham khảo: https://github.com/emantzoo/powerbi-code-first-dashboards (không chép lại bộ helper; mã dự án viết riêng).
- Microsoft PBIR: https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report
- Microsoft TMDL: https://learn.microsoft.com/en-us/analysis-services/tmdl/tmdl-overview

File CSV người dùng cung cấp là nguồn số liệu thực tế của báo cáo; không lấy con số trên catalog để thay thế bản xuất.
'''
    (ROOT/'reports/CASE_STUDY_VI.md').write_text(case,encoding='utf-8')
    con.close();print('Built offline preview and Vietnamese case study.')

if __name__=='__main__':main()
