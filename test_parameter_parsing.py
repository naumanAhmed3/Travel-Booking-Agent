import unittest
from extract_parameters import extract_passenger_count  # Adjust to your module

class TestExtractPassengerCount(unittest.TestCase):

    def test_single_person(self):
        self.assertEqual(extract_passenger_count("I want to go to Karachi"), {"adults": 1, "children": 0, "infants": 0})

    def test_with_wife(self):
        self.assertEqual(extract_passenger_count("I want to travel with my wife"), {"adults": 2, "children": 0, "infants": 0})

    def test_with_parents(self):
        self.assertEqual(extract_passenger_count("Book a flight for me and my parents"), {"adults": 3, "children": 0, "infants": 0})

    def test_with_friends(self):
        self.assertEqual(extract_passenger_count("Traveling with two friends"), {"adults": 3, "children": 0, "infants": 0})

    def test_with_kids(self):
        self.assertEqual(extract_passenger_count("I want to travel with my wife and 2 kids"), {"adults": 2, "children": 2, "infants": 0})

    def test_with_children_variation(self):
        self.assertEqual(extract_passenger_count("Traveling with three children"), {"adults": 1, "children": 3, "infants": 0})

    def test_with_infant(self):
        self.assertEqual(extract_passenger_count("I will bring an infant with me"), {"adults": 1, "children": 0, "infants": 1})

    def test_with_baby(self):
        self.assertEqual(extract_passenger_count("Me and my wife and our baby"), {"adults": 2, "children": 0, "infants": 1})

    def test_full_family(self):
        self.assertEqual(extract_passenger_count("I’m traveling with my wife, two kids, and a baby"), {"adults": 2, "children": 2, "infants": 1})

    def test_group_mention(self):
        self.assertEqual(extract_passenger_count("We are five friends traveling"), {"adults": 5, "children": 0, "infants": 0})

    def test_couple_only(self):
        self.assertEqual(extract_passenger_count("Just me and my husband"), {"adults": 2, "children": 0, "infants": 0})

    def test_with_brother_sister(self):
        self.assertEqual(extract_passenger_count("Traveling with my brother and sister"), {"adults": 3, "children": 0, "infants": 0})

    def test_multiple_families(self):
        self.assertEqual(extract_passenger_count("Two couples and 4 kids"), {"adults": 4, "children": 4, "infants": 0})

    def test_family_of_five(self):
        self.assertEqual(extract_passenger_count("We are a family of 5"), {"adults": 5, "children": 0, "infants": 0})

    def test_edge_zero_kids(self):
        self.assertEqual(extract_passenger_count("I'm traveling with my wife, no kids"), {"adults": 2, "children": 0, "infants": 0})

    def test_just_children(self):
        self.assertEqual(extract_passenger_count("2 kids and 1 infant will travel"), {"adults": 0, "children": 2, "infants": 1})

    def test_plural_variations(self):
        self.assertEqual(extract_passenger_count("Traveling with babies, kids and adults"), {"adults": 3, "children": 2, "infants": 2})  # heuristic default fallback

    def test_group_with_number(self):
        self.assertEqual(extract_passenger_count("3 adults, 2 children, 1 infant"), {"adults": 3, "children": 2, "infants": 1})

    def test_us(self):
        self.assertEqual(extract_passenger_count("Book tickets for us"), {"adults": 2, "children": 0, "infants": 0})  # heuristic

    def test_ambiguous_few_people(self):
        self.assertEqual(extract_passenger_count("A few people are going"), {"adults": 3, "children": 0, "infants": 0})  # heuristic

    def test_big_family_trip(self):
        self.assertEqual(extract_passenger_count("I will go with my family of 7"), {"adults": 7, "children": 0, "infants": 0})

    def test_only_infant_word(self):
        self.assertEqual(extract_passenger_count("Infant"), {"adults": 0, "children": 0, "infants": 1})

    def test_no_people_mentioned(self):
        self.assertEqual(extract_passenger_count("Just want to fly"), {"adults": 1, "children": 0, "infants": 0})

if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestLoader().loadTestsFromTestCase(TestExtractPassengerCount))
    print("\nTest Summary:")
    print(f"  Total tests run   : {result.testsRun}")
    print(f"  Failures          : {len(result.failures)}")
    print(f"  Errors            : {len(result.errors)}")
    if not result.failures and not result.errors:
        print("  ✅ All tests passed!")
    else:
        print("  ❌ Some tests failed.")
