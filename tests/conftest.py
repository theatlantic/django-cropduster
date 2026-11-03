import os
import warnings

import pytest
from django.test import TestCase, override_settings


TestCase.pytestmark = pytest.mark.django_db(transaction=True, reset_sequences=True)


@pytest.fixture(scope="session", autouse=True)
def s3_server():
    """Starts a moto S3 server and points default_storage at it when S3=1 is set"""
    if os.environ.get("S3") != "1":
        yield None
        return

    from django.conf import settings
    from django.core.files.storage import default_storage
    from tests.moto_server import MotoServer

    with MotoServer() as server:
        with override_settings(
                AWS_S3_ENDPOINT_URL=server.endpoint_url, STORAGES=settings.STORAGES):
            assert default_storage.endpoint_url == server.endpoint_url, (
                "default_storage does not use the moto server's endpoint")
            default_storage.connection.meta.client.create_bucket(
                Bucket=default_storage.bucket_name)
            yield server


@pytest.fixture(autouse=True)
def suppress_warnings():
    warnings.simplefilter("error", Warning)
    warnings.filterwarnings('ignore', message='.*?ckeditor')
    warnings.filterwarnings('ignore', message='.*?collections')
    warnings.filterwarnings('ignore', message='.*?Resampling')
    warnings.filterwarnings('ignore', message='.*?distutils')
    # warning from grappelli 3.0 templates
    warnings.filterwarnings('ignore', message='.*?length_is')
