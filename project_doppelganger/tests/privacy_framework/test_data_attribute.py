import unittest
from project_doppelganger.src.privacy_framework.data_attribute import DataAttribute, DataCategory, Purpose

class TestDataAttribute(unittest.TestCase):

    def test_data_category_serialization(self):
        category = DataCategory.COMMUNICATION_CONTENT
        self.assertEqual(category.to_dict(), "Communication Content")
        self.assertEqual(DataCategory.from_dict("Communication Content"), category)
        with self.assertRaises(ValueError):
            DataCategory.from_dict("Invalid Category")

    def test_purpose_serialization(self):
        purpose = Purpose.PERSONA_CREATION
        self.assertEqual(purpose.to_dict(), "Persona Creation")
        self.assertEqual(Purpose.from_dict("Persona Creation"), purpose)
        with self.assertRaises(ValueError):
            Purpose.from_dict("Invalid Purpose")

    def test_data_attribute_serialization(self):
        attr = DataAttribute(
            name="UserQuery",
            category=DataCategory.COMMUNICATION_CONTENT,
            description="A query made by the user to their persona.",
            sensitivity_level=3
        )
        attr_dict = attr.to_dict()
        expected_dict = {
            "name": "UserQuery",
            "category": "Communication Content",
            "description": "A query made by the user to their persona.",
            "sensitivity_level": 3
        }
        self.assertEqual(attr_dict, expected_dict)

        attr_from_dict = DataAttribute.from_dict(expected_dict)
        self.assertEqual(attr_from_dict, attr)

    def test_data_attribute_serialization_all_enums(self):
        for category in DataCategory:
            for purpose_enum_member in Purpose: # Keep distinct from Purpose class itself
                attr = DataAttribute(
                    name=f"Test_{category.name}_{purpose_enum_member.name}",
                    category=category,
                    description="Test description",
                    sensitivity_level=1
                )
                attr_dict = attr.to_dict()
                attr_from_dict = DataAttribute.from_dict(attr_dict)
                self.assertEqual(attr_from_dict, attr, f"Failed for category {category} and purpose {purpose_enum_member}")


if __name__ == '__main__':
    unittest.main()
