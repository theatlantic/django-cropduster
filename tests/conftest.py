import warnings

import pytest
from django.test import TestCase


TestCase.pytestmark = pytest.mark.django_db(transaction=True, reset_sequences=True)


@pytest.fixture(autouse=True)
def suppress_warnings():
    warnings.simplefilter("error", Warning)
    warnings.filterwarnings('ignore', message='.*?ckeditor')
    warnings.filterwarnings('ignore', message='.*?collections')
    warnings.filterwarnings('ignore', message='.*?Resampling')
    warnings.filterwarnings('ignore', message='.*?distutils')
    # warning from grappelli 3.0 templates
    warnings.filterwarnings('ignore', message='.*?length_is')
