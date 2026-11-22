"""Fabricated interval/policy checks and static planning consistency only."""
import unittest
from .audit import OUT,ROOT,read,conflict

class PlanningQA(unittest.TestCase):
    def setUp(self):self.plan=read(OUT/'COLLECTION_AND_PARTITION_PLAN.json')
    def test_overlap_warmup_embargo_and_touching_boundaries(self):
        a={'warmup_start_s':0,'scored_end_s':10000}
        for start in (9999,10000,13599,13600):
            with self.subTest(start=start):self.assertTrue(conflict(a,{'warmup_start_s':start,'scored_end_s':20000}))
        self.assertFalse(conflict(a,{'warmup_start_s':13601,'scored_end_s':30000}))
    def test_all_plans_pairwise_disjoint(self):
        for name in ('minimum','recommended','expanded'):
            groups=self.plan[name]
            for i,a in enumerate(groups):
                self.assertEqual(a['scored_end_s']-a['scored_start_s'],259200)
                self.assertEqual(a['scored_start_s']-a['warmup_start_s'],604800)
                for b in groups[i+1:]:self.assertFalse(conflict(a,b),(name,a['group_id'],b['group_id']))
    def test_exposed_components_development_only(self):
        for name in ('minimum','recommended','expanded'):
            for g in self.plan[name]:
                if any(conflict(g,e) for e in self.plan['existing_exposed_footprints']):self.assertEqual(g['partition'],'development')
    def test_recommended_counts_and_seasons(self):
        groups=self.plan['recommended'];self.assertEqual(len(groups),16)
        expected={'development':8,'validation':4,'protected_final_test':4}
        for part,count in expected.items():
            selected=[g for g in groups if g['partition']==part]
            self.assertEqual(len(selected),count)
            self.assertEqual(set(g['calendar_regime_bin'] for g in selected),{'winter','spring','summer','autumn'})
    def test_no_protected_promotion_on_expansion(self):
        recommended={g['group_id']:g for g in self.plan['recommended']}
        for name in ('minimum','expanded'):
            for g in self.plan[name]:
                if g['group_id'] in recommended:self.assertEqual(g['partition'],recommended[g['group_id']]['partition'])
    def test_selected_peak_days_in_target_custom_windows(self):
        groups={g['start_day_offset']:g for g in self.plan['recommended']}
        for start,selected in ((20,21),(288,289),(340,341)):
            g=groups[start];self.assertLessEqual(g['scored_start_s'],selected*86400);self.assertLess(selected*86400,g['scored_end_s'])
        self.assertEqual(groups[340]['partition'],'protected_final_test')
    def test_budget_arithmetic_and_no_fake_repeats(self):
        for b in read(OUT/'BUDGET_CALCULATIONS.json')['plans']:
            self.assertEqual(b['runs_total'],2*b['temporal_dependency_groups_total'])
            self.assertEqual(b['new_simulation_instances'],b['runs_total']-4)
            self.assertEqual(b['new_scored_advances'],864*b['new_simulation_instances'])
            self.assertEqual(b['projected_joint_origins'],852*b['runs_total'])
            self.assertEqual(b['projected_numeric_targets'],b['projected_joint_origins']*8)
    def test_168_features_and_all_requested_fields(self):
        inv=read(OUT/'VARIABLE_INVENTORY.json');self.assertEqual(len(inv['audited_D1P_features']),168)
        required={'name','unit','source','status','available_at_prediction','purpose','relevance','missing_data_limitations','leakage_risk'}
        for collection in ('audited_D1P_features','API_catalog','proposed_derived_constants_metadata_targets'):
            for variable in inv[collection]:self.assertTrue(required<=set(variable),(collection,variable['name']))
        self.assertEqual(inv['constant_D1P_feature_count'],30)
    def test_thermal_source_coefficients_not_fitted(self):
        spec=read(OUT/'BUILDING_SPECIFICATIONS.json')
        values={v['name']:v['value'] for v in spec['verified_static_parameters']}
        self.assertEqual(float(values['mod.fcu.COP']),3.)
        self.assertEqual(float(values['mod.fcu.eff']),.9)
        self.assertEqual(spec['source_thermal_proxy_formulas']['signed_airside_HVAC_W'],'0.9*PHea_gas - 3*PCoo_electric')
        self.assertTrue(spec['derived_material_properties']['extWalCase900']['not_an_identified_whole_zone_RC_parameter'])
    def test_scenario_names_not_season_or_selected_prefix(self):
        scenario=read(OUT/'SCENARIO_AND_WEATHER_AUDIT.json')
        self.assertEqual(len(scenario['scenarios']),5)
        self.assertTrue(all(not s['source_selected_day_in_first_72h'] for s in scenario['scenarios']))
        self.assertEqual(next(s for s in scenario['scenarios'] if s['key']=='mix_day')['source_selected_day'],21)
    def test_documents_complete_no_unfilled_templates(self):
        for name in ('COLLECTION_PLAN','VARIABLE_INVENTORY','RC_READINESS','PARTITION_PLAN','QA_AND_BUDGET','TEAM_HANDOFF_PLAN'):
            text=(ROOT/f'STAGE4E_D2_{name}.md').read_text(encoding='utf-8')
            self.assertNotIn('<!--',text);self.assertIn('PLANNING',text.upper())
    def test_old_evidence_intact(self):
        from stage4e_d1_v2.runner import verify_frozen,sha
        self.assertEqual(verify_frozen(),'ec9c64f9abffcda7095d537e375eda7bb8f6b6d367aa1aa2238bcc606bcbeb5c')
        manifest=ROOT/'stage4e_d1p/PREVIEW_DELIVERY_MANIFEST.json'
        self.assertEqual(sha(manifest),'5da0d933b18ea68f719e52a18d5846a15e2cb28c57c3bbfc8f69322ec415b014')
        for name,digest in read(manifest)['files'].items():self.assertEqual(sha(ROOT/name),digest,name)

if __name__=='__main__':unittest.main(verbosity=2)
