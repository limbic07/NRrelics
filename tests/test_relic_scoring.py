import unittest
import json

from core.relic_matcher import match_relic
from core.relic_scoring import normalize_scoring
from core.preset_manager import PresetManager


def observed(*positives, negatives=()):
    return {
        "success": True,
        "affixes": ([{"cleaned_text": name, "is_positive": True} for name in positives]
                    + [{"cleaned_text": name, "is_positive": False} for name in negatives]),
    }


def preset(*names, grades=None, dedicated=True):
    return {"id": "build", "name": "build", "affixes": list(names),
            "affix_tiers": grades or {}, "is_active": True,
            "required_affix_groups": [] if dedicated else None}


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.scoring = normalize_scoring({"enabled": True})
        self.negative = "持续减少血量"

    def match(self, observation, general, dedicated, threshold=2, **kwargs):
        return match_relic(observation, general, [dedicated], threshold=threshold,
                           scoring_config=self.scoring, mode="deepnight", **kwargs)

    def test_double_and_triple_are_independent_of_score(self):
        build = preset("a", "b", grades={"a": "core", "b": "secondary"})
        self.assertTrue(self.match(observed("a", "b"), None, build, 2).qualified)
        self.assertFalse(self.match(observed("a", "b"), None, build, 3).qualified)

    def test_two_core_secondary_unacceptable_is_backup_in_both_modes(self):
        build = preset("a", "b", "c", grades={"a": "core", "b": "core", "c": "secondary"})
        for threshold in (2, 3):
            result = self.match(observed("a", "b", "c", negatives=(self.negative,)),
                                None, build, threshold)
            self.assertTrue(result.qualified)
            self.assertEqual(result.best_match.score, 14)
            self.assertEqual(result.best_match.score_grade, "backup")
            self.assertFalse(result.perfect)

    def test_three_weak_positives_fail_score_gate(self):
        build = preset("a", "b", "c", grades={n: "bonus" for n in "abc"})
        self.assertFalse(self.match(observed("a", "b", "c"), None, build, 3).qualified)

    def test_inherited_grade_can_be_overridden_once(self):
        general = preset("a", grades={"a": "bonus"}, dedicated=False)
        build = preset("b", grades={"a": "core", "b": "secondary"})
        result = self.match(observed("a", "b"), general, build)
        self.assertTrue(result.qualified)
        self.assertEqual(result.best_match.score, 16)
        self.assertEqual(result.best_match.effective_count, 2)

    def test_same_affix_in_general_and_dedicated_counts_once(self):
        general = preset("a", grades={"a": "bonus"}, dedicated=False)
        build = preset("a", "b", grades={"a": "core", "b": "secondary"})
        result = self.match(observed("a", "b"), general, build, 3)
        self.assertFalse(result.qualified)
        self.assertEqual(result.preset_matches[0].effective_count, 2)

    def test_preset_grade_json_round_trip_and_legacy_default(self):
        grades = PresetManager._checked_tiers(["b"],
                                              {"b": "bonus", "a": "secondary"}, {"a"})
        general = json.loads(json.dumps({"affixes": ["a"]}))  # Legacy: no grade field.
        build = json.loads(json.dumps(preset("b", grades=grades)))
        result = match_relic(observed("a", "b"), general, [build],
                             scoring_config=self.scoring)
        self.assertEqual(result.preset_matches[0].score, 8)

    def test_scoring_blacklist_is_penalty_unless_hard_enabled(self):
        build = preset("a", "b", "c", grades={"a": "core", "b": "core", "c": "secondary"})
        blacklist = {"affixes": [self.negative], "is_active": True}
        observation = observed("a", "b", "c", negatives=(self.negative,))
        self.assertTrue(match_relic(observation, None, [build], blacklist,
                                    scoring_config=self.scoring, mode="deepnight").qualified)
        self.scoring["hard_blacklist"] = True
        self.assertFalse(match_relic(observation, None, [build], blacklist,
                                     scoring_config=self.scoring, mode="deepnight").qualified)

    def test_custom_weights_and_negative_grade(self):
        self.scoring["deepnight"]["positive"]["core"] = 13
        self.scoring["negative_tiers"][self.negative] = "harmful"
        build = preset("a", "b", grades={"a": "core", "b": "core"})
        result = self.match(observed("a", "b", negatives=(self.negative,)), None, build)
        self.assertEqual(result.best_match.score, 22)
        self.assertEqual(result.best_match.score_grade, "keep")

    def test_negative_can_be_positive_for_one_build(self):
        general = preset("a", grades={"a": "core"}, dedicated=False)
        build = preset("b", grades={"b": "secondary"})
        build["negative_tiers"] = {self.negative: "core"}
        result = self.match(observed("a", "b", negatives=(self.negative,)),
                            general, build, threshold=3)
        self.assertTrue(result.qualified)
        self.assertEqual(result.best_match.effective_count, 3)
        self.assertEqual(result.best_match.score, 26)
        self.assertIn(self.negative, result.best_match.matched_affixes)

    def test_dedicated_negative_overrides_general(self):
        general = preset("a", grades={"a": "core"}, dedicated=False)
        general["negative_tiers"] = {self.negative: "core"}
        build = preset("b", grades={"b": "secondary"})
        build["negative_tiers"] = {self.negative: "harmful"}
        result = self.match(observed("a", "b", negatives=(self.negative,)),
                            general, build)
        self.assertEqual(result.preset_matches[0].effective_count, 2)
        self.assertEqual(result.preset_matches[0].score, 12)

    def test_dedicated_can_exclude_inherited_positive(self):
        general = preset("a", "b", grades={"a": "core", "b": "core"}, dedicated=False)
        build = preset("c", grades={"c": "core"})
        build["excluded_affixes"] = ["b"]
        result = self.match(observed("a", "b", "c"), general, build, threshold=3)
        self.assertFalse(result.qualified)
        self.assertEqual(result.preset_matches[0].effective_count, 2)

    def test_normal_mode_has_no_negative_scores(self):
        build = preset("a", "b", grades={"a": "core", "b": "secondary"})
        result = match_relic(observed("a", "b", negatives=(self.negative,)),
                             None, [build], scoring_config=self.scoring, mode="normal")
        self.assertTrue(result.qualified)
        self.assertEqual(result.best_match.score, 16)

    def test_old_mode_retains_original_count_and_blacklist(self):
        build = preset("a", "b", "c")
        blacklist = {"affixes": [self.negative], "is_active": True}
        observation = observed("a", "b", negatives=(self.negative,))
        self.assertFalse(match_relic(observation, None, [build], blacklist).qualified)
        self.assertTrue(match_relic(observed("a", "b"), None, [build], threshold=2).qualified)


if __name__ == "__main__":
    unittest.main()
