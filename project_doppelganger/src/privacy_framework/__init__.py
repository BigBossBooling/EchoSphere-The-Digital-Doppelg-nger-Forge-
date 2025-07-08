# This file makes Python treat the 'privacy_framework' directory as a package.

from .data_attribute import DataAttribute, DataCategory, Purpose
from .consent import UserConsent, ConsentStatus
from .policy import PrivacyPolicy
