import os
import xlsxwriter
from werkzeug.exceptions import BadRequest
from http import HTTPStatus

from src.models.model_db_methods.user_db_methods import UserDBMethods
from src.utils.s3_client import S3Client
from src.extensions import config
from src.common_constants.tasks_constants import EMAIL_SUBJECT, EMAIL_CONTENT
from src.utils.send_email import send_email


def build_excel_and_send_email_task(self, data, exchange=None):
    start_date = data.pop("start_date")
    end_date = data.pop("end_date")
    report_name = data.pop("report_name")

    for user_id, aggregated_data in data.items():
        if (user := UserDBMethods.get_record_with_id(user_id)) and (
            user_email := user.email
        ):
            report_name_with_id = build_excel_with_provided_data(
                aggregated_data, start_date, end_date, report_name, user_id
            )
            file_url = send_email_to_user(
                user_email, user.username, report_name_with_id, start_date, end_date
            )
            print(f"\nfile_url : {file_url}\n")


def build_excel_with_provided_data(
    aggregated_data, start_date, end_date, report_name, user_id
):
    report_name_with_id = f"{report_name}_for_{user_id}.xlsx"
    workbook = xlsxwriter.Workbook(report_name_with_id)
    worksheet = workbook.add_worksheet()
    bold_words = workbook.add_format({"bold": True})
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
        summation_count_from = []
        topup_summation_count_from = []

        for item, cost in related_data.items():
            worksheet.merge_range(row_count, col_count, row_count, col_count + 1, item)
            formatted_cost = cost if cost > 0 else f"+{abs(cost)}"
            worksheet.write(row_count, col_count + 2, formatted_cost)
            (summation_count_from if cost > 0 else topup_summation_count_from).append(cost)
            row_count += 1

        worksheet.merge_range(
            row_count, col_count, row_count, col_count + 1, "TOTAL", bold_words
        )
        worksheet.write(
            row_count,
            col_count + 2,
            f"+{abs(sum(topup_summation_count_from))}, {sum(summation_count_from)}",
            bold_words,
        )
        row_count += 1
        worksheet.merge_range(row_count, col_count, row_count, col_count + 1, "")
        row_count += 1

    workbook.close()
    return report_name_with_id


def send_email_to_user(user_email, user_name, report_name, start_date, end_date):
    s3 = S3Client()
    with open(report_name, "rb") as excel_file:
        file_url = s3.upload_public_file_obj(
            excel_file,
            config.get("AWS_BUCKET_NAME"),
            key=f"{config.get('EXCEL_UPLOAD_PATH')}/{report_name}",
        )
        if not file_url:
            raise BadRequest(
                "There was an exception while uploading Excel. Please try again."
            )

    response = send_email(
        to_addr=user_email,
        subject=EMAIL_SUBJECT.format(date_ranges=f"{start_date} to {end_date}"),
        content=EMAIL_CONTENT.format(user_name=user_name, file_url=file_url)
    )

    if response.status_code == HTTPStatus.OK:
        print(f"SENT email to {user_email}")

    if not os.remove(report_name):
        return file_url
    raise BadRequest("Error while deleting the excel file.")
