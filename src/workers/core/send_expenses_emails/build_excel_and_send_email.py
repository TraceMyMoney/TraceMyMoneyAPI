import xlsxwriter

from src.models.model_db_methods.user_db_methods import UserDBMethods


def build_excel_and_send_email_task(self, data, exchange=None):
    start_date = data.pop("start_date")
    end_date = data.pop("end_date")
    report_name = data.pop("report_name")

    for user_id, aggregated_data in data.items():
        if (user := UserDBMethods.get_record_with_id(user_id)) and (
            user_email := user.email
        ):
            built_excel_book = build_excel_with_provided_data(
                aggregated_data, start_date, end_date, report_name
            )
            send_email_to_user(user_email, built_excel_book)


def build_excel_with_provided_data(aggregated_data, start_date, end_date, report_name):
    workbook = xlsxwriter.Workbook(f"{report_name}.xlsx")
    worksheet = workbook.add_worksheet()
    bold_words = workbook.add_format({"bold": True,})
    bold_words_with_centered = workbook.add_format({"bold": True, "align": "center"})
    centered_bold = workbook.add_format(
        {
            "bold": True,
            "align": "center",
            "valign": "vcenter",
            "font_color": "white",
            "bg_color": "#1E90FF",
            "border": 1,
        }
    )
    worksheet.merge_range(
        0, 0, 0, 4, f"From {start_date[:10]} to {end_date[:10]}", bold_words_with_centered
    )
    row_count = 1
    col_count = 0
    for bank_name, related_data in aggregated_data.items():
        worksheet.merge_range(
            row_count, col_count, row_count, col_count + 1, bank_name, centered_bold
        )
        row_count += 1
        summation_count_from = row_count

        for item, cost in related_data.items():
            worksheet.merge_range(row_count, col_count, row_count, col_count + 1, item)
            worksheet.write(row_count, col_count + 2, cost)
            row_count += 1

        worksheet.merge_range(
            row_count, col_count, row_count, col_count + 1, "TOTAL", bold_words
        )
        worksheet.write(
            row_count,
            col_count + 2,
            f"=SUM(C{summation_count_from + 1}:C{row_count})",
            bold_words,
        )
        row_count += 1
        worksheet.merge_range(row_count, col_count, row_count, col_count + 1, "")
        row_count += 1

    workbook.close()


def send_email_to_user(user_email, built_excel_book):
    pass
