import boto3
from abc import ABC, abstractmethod
from typing import Optional
from botocore.exceptions import BotoCoreError, ClientError
from flask import current_app as app


class AbstractS3Client(ABC):

    @abstractmethod
    def upload_file_obj(self, file_obj, bucket_name, key) -> str:
        pass

    @abstractmethod
    def upload_public_file_obj(self, file_obj, bucket_name, key) -> str:
        pass

    @abstractmethod
    def get_s3_object_url(self, bucket_name, key) -> str:
        pass


class S3Client(AbstractS3Client):
    def __init__(self):
        self.client = boto3.client(
            "s3",
            aws_access_key_id=app.config["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=app.config["AWS_SECRET_ACCESS_KEY"],
        )

    def upload_file_obj(self, file_obj, bucket_name, key) -> Optional[str]:
        try:
            self.client.upload_fileobj(file_obj, bucket_name, key)
        except (BotoCoreError, ClientError) as ex:
            app.logger.error(f"There was an exception while uploading file. {ex}")
            return None
        return self.get_s3_object_url(bucket_name, key)

    def upload_public_file_obj(self, file_obj, bucket_name, key) -> Optional[str]:
        try:
            self.client.upload_fileobj(
                file_obj, bucket_name, key, ExtraArgs={"ACL": "public-read"}
            )
        except (BotoCoreError, ClientError) as ex:
            app.logger.error(f"There was an exception while uploading file. {ex}")
            return None
        return self.get_s3_object_url(bucket_name, key)

    def get_s3_object_url(self, bucket_name, key) -> Optional[str]:
        try:
            location = self.client.get_bucket_location(Bucket=bucket_name)[
                "LocationConstraint"
            ]
        except (BotoCoreError, ClientError) as ex:
            app.logger.error(f"There was an exception while fetching file. {ex}")
            return None
        return f"https://{bucket_name}.s3-{location}.amazonaws.com/{key}"
