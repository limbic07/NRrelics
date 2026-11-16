import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer, QCoreApplication, QEvent
from core.loadout_metrics import Metrics, equivalence_key
from ui.dialogs.deep_results import ResultModel, ResultFilter, DeepResultsDialog
from ui.pages.page_relics import LoadoutResultDialog


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def presets(name):
    data = json.loads(Path('data/default_presets.json').read_text(encoding='utf-8'))
    manager = SimpleNamespace(**data)
    n = next(p for p in data['normal_dedicated'].values() if p['name'] == name)
    d = next(p for p in data['deepnight_whitelist_dedicated'].values() if p['name'] == name)
    return Metrics(manager, {}, n['id'], d['id'])


def solution(affixes, official=None, identifier=1, score=20):
    return dict(score=score, vessel='test', relics=[dict(id=identifier, relic_type='normal', color='绿',
                 affixes=affixes, official_id=official, slot_index=0, affix_points={})])


def test_glass_necklace_and_first_hit():
    metrics = presets('送葬者｜非战技物理·直剑')
    labels = [x[0] for x in metrics.scenarios]
    assert any('第一击＋连击' in x for x in labels)
    value = metrics.evaluate(solution(['连续攻击时，提升攻击力', '强化轻攻击的第一记攻击'], 92))
    index = labels.index('普攻／直剑／无指定目标状态／第一击＋连击')
    assert value['damage'][index] == pytest.approx(40.3)
    empty = metrics.evaluate(solution(['连续攻击时，提升攻击力']))
    assert empty['damage'][index] == 0  # official eligibility must not leak to ordinary relics


def test_poison_bow_scenarios():
    m = presets('铁之眼｜毒弓铁眼')
    labels = [s[0] for s in m.scenarios]
    assert any('中毒目标' in s for s in labels)
    assert not any('腐败目标' in s or '冻伤目标' in s for s in labels)
    assert all('melee' not in tags for label, tags in m.scenarios if '普攻／弓' in label)
    result = m.evaluate(solution(['提升弓的攻击力','对陷入中毒的敌人，能强化攻击']))
    index = labels.index('普攻／弓／中毒目标／基础')
    assert result['damage'][index] == pytest.approx(16.6)


def test_official_utility_requires_effective_affix():
    m=presets('铁之眼｜毒弓铁眼')
    name='自然累积绝招量表+3'
    s=solution([name,'对陷入中毒的敌人，能强化攻击'],19)
    m.maps['normal'].pop(name,None)
    assert name not in m.evaluate(s)['functional_terms']
    m.maps['normal'][name]=2
    assert m.evaluate(s)['functional_terms'][name]==1
    m.maps['normal'][name]=0
    assert name not in m.evaluate(s)['functional_terms']
    m.maps['normal'][name]=-4;s['relics'][0]['affix_points'][name]=-4
    m.negative_names['normal'].add(name)
    value=m.evaluate(s)
    assert name not in value['functional_terms'] and value['negative_terms'][name]==1


def test_gravity_is_magic():
    m = presets('女爵｜重力·法爵')
    label, tags = next(s for s in m.scenarios if s[0].startswith('法术／重力'))
    assert {'spell','魔力','element'} <= tags
    assert 'physical' not in tags and 'melee' not in tags


def test_survival_and_functional_character_effects():
    m = presets('送葬者｜非战技物理·直剑')
    # Approve each tested utility/survival effect explicitly. An arbitrary
    # official ID must not make unrelated affixes effective.
    m.maps['normal'].update({'提升血量上限':2, '提升物理减伤率+1':2, '【送葬者】发动绝招时，提升攻击力':2})
    s = solution(['提升血量上限', '提升物理减伤率+1', '【送葬者】发动绝招时，提升攻击力'], 92)
    value = m.evaluate(s)
    assert value['survival']['survival_physical'] == pytest.approx((1.1/.895-1)*100)
    assert value['survival']['survival_element'] == pytest.approx(10)
    assert value['functions']==1
    assert all(v==0 for v in value['damage'])


def test_cancel_before_native_solve():
    from core.loadout_optimizer import optimize, load_catalog
    data=json.loads(Path('data/default_presets.json').read_text(encoding='utf-8'))
    manager=SimpleNamespace(**data)
    p=next(p for p in data['normal_dedicated'].values() if p['name']=='铁之眼｜毒弓铁眼')
    _, vessels=load_catalog()
    relics=[dict(id=i,relic_type='normal',color='绿',affixes=['提升弓的攻击力']) for i in range(3)]
    with pytest.raises(InterruptedError):
        optimize({'hero':'铁之眼'},relics,vessels,manager,{},normal_preset_id=p['id'],
                 deepnight_preset_id='none',page_size=10,cancelled=lambda:True)


def test_equivalence_preserves_function_and_negative_identity():
    a = solution(['提升血量上限'])
    b = solution(['提升血量上限'], identifier=2)
    assert equivalence_key(a) == equivalence_key(b)
    b['relics'][0]['affixes'] = ['提升专注值上限']
    assert equivalence_key(a) != equivalence_key(b)


def test_disk_store_sort_filter_and_cleanup(app):
    m = ResultModel(presets('铁之眼｜毒弓铁眼'))
    path = m.temp.name
    a = solution(['提升物理攻击力'], score=9)
    b = solution(['提升物理攻击力+4'], identifier=2, score=100)
    b['relics'][0]['relic_type'] = 'deepnight'
    m.append([a, a, b])
    assert len(m.rows) == 2 and m.rows[0]['count'] == 2
    assert m.solution(0, 1) == a
    proxy = ResultFilter(); proxy.setSourceModel(m); proxy.sort(0, Qt.DescendingOrder)
    assert proxy.index(0, 0).data(Qt.UserRole) == 100
    proxy.bounds[0] = (10, 20); proxy.invalidateFilter()
    assert proxy.rowCount() == 1
    m.close()
    assert not Path(path).exists()


def test_dialog_details_and_repeated_release(app):
    from qfluentwidgets import setTheme, Theme
    for theme in (Theme.LIGHT, Theme.DARK):
        setTheme(theme)
        d = DeepResultsDialog(presets('铁之眼｜毒弓铁眼'), {1:1}, LoadoutResultDialog)
        d.append({'solutions':[solution(['提升物理攻击力'])]})
        d.show(); app.processEvents()
        d._details(0)
        app.processEvents()
        assert d.detail is not None
        d.detail.accept()
        path = d.model.temp.name
        d.release()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        assert not Path(path).exists()


def test_deep_worker_batches_and_ordinary_mode(app, monkeypatch):
    import copy
    import time
    from ui.pages.page_relics import RelicPage
    data = json.loads(Path('data/default_presets.json').read_text(encoding='utf-8'))
    class Manager(SimpleNamespace):
        def get_dedicated_presets(self, mode):
            return self.normal_dedicated if mode == 'normal' else self.deepnight_whitelist_dedicated
    page = RelicPage(Manager(**data), 'optimizer')
    page.groups = []
    calls = []
    def fake(*args, **kwargs):
        calls.append(kwargs)
        if 'solution_callback' in kwargs:
            for identifier in (1, 2):
                kwargs['solution_callback'](dict(score=20,min_score=15,min_ratio=.75,
                    solutions=[solution(['提升物理攻击力'],identifier=identifier)],has_more=True))
            return dict(score=20,min_score=15,min_ratio=.75,solutions=[],has_more=False)
        return dict(score=20, min_score=15, min_ratio=.75,
                    solutions=[solution(['提升物理攻击力'], identifier=len(calls))],
                    excluded_combinations=[[i] for i in range(1, len(calls)+1)], has_more=len(calls)==1)
    monkeypatch.setattr('ui.pages.page_relics.optimize', fake)
    def isolated(args,kwargs,cancelled,publish,progress,log_path):
        publish(fake(*args,**kwargs,solution_callback=publish))
    monkeypatch.setattr('core.optimizer_process.run_isolated',isolated)
    page.optimization_mode.setCurrentIndex(1)
    page.deep_limit.setValue(100)
    page._solve()
    deadline = time.monotonic()+5
    while (page.worker is not None or page.deep_running) and time.monotonic()<deadline:
        app.processEvents(); time.sleep(.005)
    assert page.worker is None and len(calls)==1
    assert page.deep_limit_value==100
    assert len(page.deep_dialog.model.rows)==1
    assert page.deep_dialog.model.rows[0]['count']==2
    assert page.seen_combinations==[] and page.result_pages==[]
    page.optimization_mode.setCurrentIndex(0)
    page._solve()
    while page.worker is not None and time.monotonic()<deadline:
        app.processEvents(); time.sleep(.005)
    assert len(calls)==2 and len(page.result_pages)==1
    assert page.deep_dialog is None
    page.release_results(); page.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_stream_matches_ranked_search_and_keeps_partial_on_stop():
    from core.loadout_optimizer import optimize
    names=['提升物理攻击力','提升物理攻击力+1']
    p=dict(affixes=names,affix_tiers={names[0]:'core',names[1]:'secondary'})
    manager=SimpleNamespace(normal_general={'affixes':[]},deepnight_general={'affixes':[]},
                            normal_dedicated={'test':p},deepnight_whitelist_dedicated={})
    items=[dict(id=i,relic_type='normal',color='红',affixes=[names[i%2]]) for i in range(6)]
    vessels=[dict(name_en='test',hero_en='Ironeye',normal_en='Red, Red, Red',deep_en='Red, Red, Red')]
    args=({'hero':'铁之眼'},items,vessels,manager,{})
    kwargs=dict(normal_preset_id='test',deepnight_preset_id='none',min_ratio=0,page_size=30)
    ordinary=optimize(*args,**kwargs)
    streamed=[]
    result=optimize(*args,**kwargs,solution_callback=lambda r:streamed.extend(r['solutions']))
    assert not result['has_more'] and result['excluded_combinations']==[]
    assert len(streamed)==20
    assert [s['score'] for s in streamed]==[s['score'] for s in ordinary['solutions']]
    assert {frozenset(r['id'] for r in s['relics']) for s in streamed}=={frozenset(r['id'] for r in s['relics']) for s in ordinary['solutions']}
    partial=[]
    with pytest.raises(InterruptedError):
        optimize(*args,**kwargs,cancelled=lambda:bool(partial),solution_callback=partial.append)
    assert len(partial)==1 and len(partial[0]['solutions'])==1


def test_details_freeze_refresh_and_do_not_reenter(app):
    d=DeepResultsDialog(presets('铁之眼｜毒弓铁眼'),{1:1},LoadoutResultDialog)
    d.append({'solutions':[solution(['提升物理攻击力'])]});d._refresh_results()
    d._details(0);detail=d.detail
    d._details(0)
    assert d.detail is detail
    d.append({'solutions':[solution(['提升物理攻击力+1'],identifier=2)]})
    assert not d.refresh_timer.isActive() and len(detail.order)==1
    for _ in range(25):detail.render()
    assert detail.findChildren(LoadoutResultDialog)==[]
    detail.accept()
    assert d.detail is None and d.proxy.rowCount()==2
    d.release();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


def test_multiple_columns_baseline_and_term_differences(app):
    m=ResultModel(presets('铁之眼｜毒弓铁眼'))
    a=solution(['提升物理攻击力','打倒敌人时，能累积绝招量表'],identifier=1)
    b=solution(['提升物理攻击力+4','打倒敌人时，能累积绝招量表+1','受到损伤时，会累积出血量表'],identifier=2)
    b['relics'][0]['relic_type']='deepnight'
    b['relics'][0]['affix_points']={'受到损伤时，会累积出血量表':-4}
    m.append([a,b]);m.set_baseline(0)
    assert m.number(1,0)==pytest.approx(8)
    assert '＋打倒敌人时，能累积绝招量表+1' in m.difference(1,'functions')
    assert '－打倒敌人时，能累积绝招量表' in m.difference(1,'functions')
    assert m.difference(1,'negatives')=='＋受到损伤时，会累积出血量表'
    m.setData(m.index(1,0),Qt.Checked,Qt.CheckStateRole)
    m.set_scenarios([0,2,3]);assert m.checked=={1} and m.baseline==0
    assert '同效方案' not in [m.title(k) for k in m.columns]
    proxy=ResultFilter();proxy.setSourceModel(m);proxy.column_bounds={0:(7.9,8.1)}
    assert proxy.rowCount()==1 and proxy.mapToSource(proxy.index(0,0)).row()==1
    m.set_baseline(None);assert m.number(1,0)==pytest.approx(12)
    m.close()


def test_baseline_clear_filters_and_popup_contents(app):
    from PySide6.QtWidgets import QTextBrowser,QTableWidget
    d=DeepResultsDialog(presets('铁之眼｜毒弓铁眼'),{},LoadoutResultDialog)
    d.append({'solutions':[solution(['提升物理攻击力'],identifier=1),solution(['提升物理攻击力+1'],identifier=2)]})
    d._refresh_results();d.proxy.column_bounds={0:(0,5),'survival_physical':(0,1),'score':(0,100),'functions':(1,2)}
    d._baseline_changed(0)
    assert d.proxy.column_bounds=={'score':(0,100)}
    d._cell_details(d.proxy.index(0,1))
    popups=[p for p in app.topLevelWidgets() if p is not d and p.findChildren(QTextBrowser)]
    assert popups and '基准方案对应词条' in popups[-1].findChild(QTextBrowser).toPlainText()
    popups[-1].close();d.model.checked={0,1};d._compare()
    popups=[p for p in app.topLevelWidgets() if p is not d and p.findChildren(QTableWidget)]
    assert popups and popups[-1].findChild(QTableWidget).columnCount()==3
    popups[-1].close();d.release();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


def test_baseline_requires_one_checked_row_and_count_filters_are_signed(app,monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from unittest.mock import Mock
    message=Mock();monkeypatch.setattr(QMessageBox,'information',message)
    d=DeepResultsDialog(presets('铁之眼｜毒弓铁眼'),{},LoadoutResultDialog)
    d.append({'solutions':[solution([],identifier=i,score=20+i) for i in range(3)]})
    d.live_timer.stop();d._refresh_results()
    # A left-selected row is not a checked row.
    d.table.setCurrentIndex(d.proxy.mapFromSource(d.model.index(2,0)))
    d._set_selected_baseline();assert d.model.baseline is None and message.call_count==1
    d.model.checked={0,2};d._set_selected_baseline()
    assert d.model.baseline is None and message.call_count==2
    for row,count in zip(d.model.rows,(2,1,4)):
        row['metrics'].update(functions=count,negatives=count)
    d.model.checked={0};d._set_selected_baseline();assert d.model.baseline==0
    for key in ('functions','negatives'):
        assert [d.model.number(i,key) for i in range(3)]==[0,-1,2]
        d.proxy.column_bounds={key:(-1,-1)};d._filter()
        assert d.proxy.rowCount()==1 and d.proxy.mapToSource(d.proxy.index(0,0)).row()==1
    d.clear_checked.click();assert not d.model.checked and d.model.baseline==0
    d.baseline_button.click();assert d.model.baseline is None and not d.proxy.column_bounds
    d.release();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


def test_inactive_blue_tear_is_not_available_in_column_selector(app,monkeypatch):
    from PySide6.QtWidgets import QDialog,QListWidget
    from core.loadout_metrics import Metrics
    manager=SimpleNamespace(normal_general={},deepnight_general={},
        normal_dedicated={'test':{'affixes':[]}},deepnight_whitelist_dedicated={})
    for active in (False,True):
        manager.normal_dedicated['test']['affixes']=['血量偏低时，能提升减伤率'] if active else []
        d=DeepResultsDialog(Metrics(manager,{},'test','none'),{},LoadoutResultDialog)
        def choose(dialog):
            choices=dialog.findChild(QListWidget)
            keys=[choices.item(i).data(Qt.UserRole) for i in range(choices.count())]
            assert ('survival_physical_blue' in keys)==active
            assert ('survival_element_blue' in keys)==active
            for i in range(choices.count()):
                choices.item(i).setCheckState(Qt.Checked if choices.item(i).data(Qt.UserRole)=='survival_element' else Qt.Unchecked)
            return QDialog.Accepted
        monkeypatch.setattr(QDialog,'exec',choose)
        d._choose_scenarios()
        assert d.model.columns==['score','survival_element','functions','negatives','detail']
        d.release();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


def test_toggle_baseline_right_click_and_button_size(app):
    from PySide6.QtTest import QTest
    from PySide6.QtGui import QContextMenuEvent
    from main import RightClickChecks
    from qfluentwidgets import setTheme,Theme
    guard=RightClickChecks();app.installEventFilter(guard)
    try:
        for theme in (Theme.LIGHT,Theme.DARK):
            setTheme(theme)
            d=DeepResultsDialog(presets('铁之眼｜毒弓铁眼'),{},LoadoutResultDialog)
            d.append({'solutions':[solution(['提升物理攻击力'])]})
            d.show();d._refresh_results();app.processEvents()
            header=d.table.horizontalHeader()
            from PySide6.QtCore import QPoint
            event=QContextMenuEvent(QContextMenuEvent.Mouse,QPoint(10,10),header.viewport().mapToGlobal(QPoint(10,10)))
            assert not guard.eventFilter(header.viewport(),event)
            d.table.setCurrentIndex(d.proxy.index(0,1))
            d.model.checked={0}
            d.baseline_button.click();assert d.model.baseline==0
            assert d.baseline_button.text()=='取消基准'
            d.baseline_button.click();assert d.model.baseline is None
            d.clear_checked.click()
            for col in range(d.model.columnCount()):
                index=d.proxy.index(0,col);d.table.scrollTo(index);app.processEvents()
                pos=d.table.visualRect(index).center()
                QTest.mouseClick(d.table.viewport(),Qt.RightButton,pos=pos)
                assert d.model.checked=={0}
                QTest.mouseClick(d.table.viewport(),Qt.RightButton,pos=pos)
                assert d.model.checked==set()
            assert d.table.rowHeight(0)>=d.table.fontMetrics().height()+16
            assert d.table.columnWidth(1)<200
            assert d.table.columnWidth(d.model.columnCount()-1)>=d.table.fontMetrics().horizontalAdvance('查看详情')+32
            d.release();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    finally:app.removeEventFilter(guard)


def test_pareto_uses_all_scenes_and_exact_terms():
    import copy
    from ui.dialogs.deep_results import dominates,pareto_rows
    from core.loadout_metrics import SURVIVAL_SCENARIOS
    a=dict(score=20,metrics=dict(damage=[10,20],survival=dict.fromkeys(SURVIVAL_SCENARIOS,10),pending=[],
                               functional_terms={'回大':1},negative_terms={'出血':1}))
    b=copy.deepcopy(a);b['metrics']['damage'][0]=11
    assert dominates(b,a) and not dominates(a,b)
    same=copy.deepcopy(a);assert not dominates(same,a)
    other=copy.deepcopy(b);other['metrics']['functional_terms']={'自然回大':1}
    assert not dominates(other,a)
    other=copy.deepcopy(b);other['metrics']['negative_terms']={'发狂':1}
    assert not dominates(other,a)
    other=copy.deepcopy(b);other['metrics']['damage'][1]=19
    assert not dominates(other,a)  # even if the second scene is hidden
    other=copy.deepcopy(b);other['metrics']['survival']['survival_element_blue']=9
    assert not dominates(other,a)  # hidden survival tradeoffs also survive
    other=copy.deepcopy(b);other['metrics']['pending']=['未知增伤']
    assert not dominates(other,a)
    other=copy.deepcopy(b);other['metrics']['negative_terms']={}
    gen=pareto_rows([a,b,other])
    with pytest.raises(StopIteration) as result:
        while True:next(gen)
    assert result.value.value==[2]


def test_selected_column_dominance_ignores_hidden_scenes_but_preserves_terms():
    import copy
    from core.loadout_metrics import dominates
    a=dict(score=20,metrics=dict(damage=[20,0],survival={'survival_physical':0,'survival_element':0},
        pending=[],functional_terms={'回大':1},negative_terms={'出血':1}))
    b=copy.deepcopy(a);b['metrics']['damage']=[10,100];b['metrics']['survival']['survival_element']=50
    columns=('score',0,'survival_physical','functions','negatives','detail')
    assert not dominates(a,b) and dominates(a,b,columns)
    assert not dominates(a,b,(*columns,1))
    assert not dominates(a,b,(*columns,'survival_element'))
    same=copy.deepcopy(b);same['metrics']['damage'][0]=20
    assert not dominates(a,same,columns)  # No strict improvement in selected columns.
    b['metrics']['functional_terms']={'其他功能':1}
    assert not dominates(a,b,columns)
    b['metrics']['functional_terms']={'回大':1};b['metrics']['negative_terms']={'发狂':1}
    assert not dominates(a,b,columns)


def test_column_cleanup_snapshot_and_resume_controls_unchanged(app):
    import time
    from unittest.mock import Mock
    d=DeepResultsDialog(presets('铁之眼｜毒弓铁眼'),{},LoadoutResultDialog)
    d.append({'solutions':[solution([f'未启用测试词条{i}'],identifier=i,score=20) for i in (1,2)]})
    d.live_timer.stop()
    d.model.rows[0]['metrics']['damage'][:2]=[20,0]
    d.model.rows[1]['metrics']['damage'][:2]=[10,100]
    d.prune_dominated(None);wait_live(app,d)
    assert len(d.model.rows)==2  # Automatic all-scene pruning retains the tradeoff.
    d.model.set_scenarios([0]);d._configure_columns();d._refresh_results()
    d.set_search_state(False,True)
    stopped=Mock();resumed=Mock()
    d.stop_requested.connect(stopped);d.resume_requested.connect(resumed)
    d._baseline_changed(1)
    d.prune_selected.click()
    # Column changes during this pass cannot change the captured comparison.
    d.model.set_scenarios([0,1])
    d.append({'solutions':[solution([],identifier=3,score=30)]})
    d.live_timer.stop()
    deadline=time.monotonic()+2
    while d.pruning is not None and time.monotonic()<deadline:
        app.processEvents();time.sleep(.001)
    d.live_timer.stop()
    assert [d.model.solution(i)['relics'][0]['id'] for i in range(len(d.model.rows))]==[1,3]
    assert d.model.baseline is None and d.prune_selected.isEnabled()
    assert d.can_resume and d.stop.isEnabled() and not stopped.called and not resumed.called
    d.stop.click();resumed.assert_called_once()
    d.release();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


def test_prune_preserves_mapping_and_defers_open_detail(app):
    import time
    d=DeepResultsDialog(presets('铁之眼｜毒弓铁眼'),{},LoadoutResultDialog)
    a=solution(['提升物理攻击力'],score=10)
    b=solution(['提升物理攻击力+1'],identifier=2,score=20)
    d.append({'solutions':[a,b]});d._refresh_results()
    d.model.checked={0,1};d._baseline_changed(0)
    d._details(0);d.prune_dominated('达到搜索上限')
    assert d.prune_pending and len(d.model.rows)==2
    d.detail.accept()
    deadline=time.monotonic()+2
    while d.pruning is not None and time.monotonic()<deadline:app.processEvents()
    assert len(d.model.rows)==1 and d.model.baseline is None
    assert '达到搜索上限' in d.status.text() and '部分结果' in d.status.text()
    assert d.model.checked=={0} and d.model.solution(0)==b
    assert d.model.db.execute('SELECT COUNT(*) FROM results').fetchone()[0]==1
    d.release();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


def test_limit_automatically_prunes_after_final_batch(app,monkeypatch):
    import time
    from ui.pages.page_relics import RelicPage
    data=json.loads(Path('data/default_presets.json').read_text(encoding='utf-8'))
    class Manager(SimpleNamespace):
        def get_dedicated_presets(self,mode):
            return self.normal_dedicated if mode=='normal' else self.deepnight_whitelist_dedicated
    page=RelicPage(Manager(**data),'optimizer');page.groups=[]
    calls=[]
    def isolated(args,kwargs,cancelled,publish,progress,log_path):
        calls.append(kwargs)
        solutions=[solution([],identifier=i,score=30 if i<50 else 24) for i in range(100)]
        publish(dict(score=30,min_score=23,min_ratio=.75,solutions=solutions,has_more=True))
        publish(dict(score=30,min_score=23,min_ratio=.75,solutions=[],has_more=True))
    monkeypatch.setattr('core.optimizer_process.run_isolated',isolated)
    page.optimization_mode.setCurrentIndex(1);page.deep_limit.setValue(100);page._solve()
    deadline=time.monotonic()+3
    while (page.worker is not None or page.deep_dialog.pruning is not None) and time.monotonic()<deadline:
        app.processEvents();time.sleep(.001)
    assert page.worker is None and page.deep_dialog.pruning is None
    assert len(calls)==1 and page.page_offset==100  # never refill after pruning
    assert len(page.deep_dialog.model.rows)==1 and page.deep_dialog.model.rows[0]['count']==50
    assert '达到搜索上限' in page.deep_dialog.status.text()
    assert '移除 1 组' in page.deep_dialog.status.text()
    page.release_results();page.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


def wait_live(app,d):
    import time
    deadline=time.monotonic()+3
    while (d.live_timer.isActive() or d.pruning is not None or d.prune_prefix<len(d.model.rows)) and time.monotonic()<deadline:
        app.processEvents();time.sleep(.001)
    assert d.pruning is None and d.prune_prefix==len(d.model.rows)


def test_live_pruning_is_incremental_and_keeps_incomparable(app):
    m=presets('铁之眼｜毒弓铁眼');m.maps['normal']['提升专注值上限']=2
    d=DeepResultsDialog(m,{},LoadoutResultDialog)
    a=solution(['打倒敌人时，能累积绝招量表'],score=10)
    b=solution(['打倒敌人时，能累积绝招量表'],identifier=2,score=20)
    d.append({'solutions':[a,b]});wait_live(app,d)
    assert len(d.model.rows)==1 and d.model.solution(0)==b
    c=solution(['提升专注值上限'],identifier=3,score=30)
    d.append({'solutions':[a,b,c]});wait_live(app,d)
    assert len(d.model.rows)==2 and d.model.rows[0]['count']==2
    assert d.pruned_count==2
    d.release();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


def test_live_snapshot_preserves_arrivals_and_open_detail(app):
    d=DeepResultsDialog(presets('铁之眼｜毒弓铁眼'),{},LoadoutResultDialog)
    a=solution([],score=10);b=solution([],identifier=2,score=20)
    d.append({'solutions':[a]});d.prune_dominated(None)
    d.append({'solutions':[b]})  # arrival after snapshot, before removal
    wait_live(app,d)
    assert len(d.model.rows)==1 and d.model.solution(0)==b
    d._details(0);opened=d.detail
    c=solution([],identifier=3,score=30)
    d.append({'solutions':[c]});d.prune_dominated(None)
    assert d.detail is opened and d.model.solution(opened.order[0])==b
    assert len(d.model.rows)==2
    opened.accept();wait_live(app,d)
    assert len(d.model.rows)==1 and d.model.solution(0)==c
    d._details(0);d.append({'solutions':[a]})
    d.release()
    assert not d.prune_timer.isActive() and not d.live_timer.isActive()
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


@pytest.mark.parametrize('dark',[False,True])
def test_colored_differences_and_comparison_reference(app,dark):
    from qfluentwidgets import setTheme,Theme
    from PySide6.QtWidgets import QTableWidget
    from ui.dialogs.deep_results import RICH_TEXT_ROLE,change_html
    setTheme(Theme.DARK if dark else Theme.LIGHT)
    d=DeepResultsDialog(presets('铁之眼｜毒弓铁眼'),{},LoadoutResultDialog)
    d.append({'solutions':[solution([],identifier=1),solution([],identifier=2,score=30)]})
    d.live_timer.stop()
    d.model.rows[0]['metrics'].update(functional_terms={'回大':1},negative_terms={'出血':1})
    d.model.rows[1]['metrics'].update(functional_terms={'回大':2,'其他功能':1},negative_terms={'发狂':1})
    d._baseline_changed(0)
    functions=d.model.data(d.model.index(1,d.model.columns.index('functions')),RICH_TEXT_ROLE)
    negatives=d.model.data(d.model.index(1,d.model.columns.index('negatives')),RICH_TEXT_ROLE)
    assert change_html('＋回大',True) in functions
    assert change_html('＋发狂',False) in negatives and change_html('－出血',True) in negatives
    d.model.checked={0,1};comparison=d._compare();table=comparison.findChild(QTableWidget)
    row=next(i for i in range(table.rowCount()) if table.item(i,0).text()=='负面｜发狂')
    assert change_html('+1 项',False) in table.item(row,2).data(RICH_TEXT_ROLE)
    table.horizontalHeader().buttons[1].click()
    assert '参照' in table.horizontalHeaderItem(2).text()
    assert change_html('-1 项',True) in table.item(row,1).data(RICH_TEXT_ROLE)
    assert '+1 项' not in table.item(row,2).text()
    d._baseline_changed(1)
    second=d._compare();second_table=second.findChild(QTableWidget)
    assert '参照' in second_table.horizontalHeaderItem(2).text()
    # Both added and removed names remain readable, including HTML metacharacters.
    assert '&lt;test&gt;' in change_html('<test>',True)
    d.show();app.processEvents();d._resize_visible_rows()
    assert d.table.rowHeight(0)>=36
    comparison.close();second.close();d.release()
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    setTheme(Theme.LIGHT)


@pytest.mark.parametrize('use_table_button',[False,True])
def test_resume_keeps_pruned_exclusions_snapshot_and_can_raise_cap(app,monkeypatch,use_table_button):
    import time
    from ui.pages.page_relics import RelicPage
    data=json.loads(Path('data/default_presets.json').read_text(encoding='utf-8'))
    class Manager(SimpleNamespace):
        def get_dedicated_presets(self,mode):
            return self.normal_dedicated if mode=='normal' else self.deepnight_whitelist_dedicated
    page=RelicPage(Manager(**data),'optimizer');page.groups=[]
    calls=[]
    def isolated(args,kwargs,cancelled,publish,progress,log_path):
        calls.append(kwargs)
        if len(calls)==1:
            publish(dict(score=30,solutions=[solution([],identifier=1,score=30),solution([],identifier=2,score=20)],has_more=True))
            deadline=time.monotonic()+3
            while not cancelled() and time.monotonic()<deadline:time.sleep(.001)
            assert cancelled()
            raise InterruptedError('manual stop')
        assert kwargs['page_size']==(198 if len(calls)==2 else 100) and kwargs['anchor_score']==30
        assert kwargs['excluded_combinations']==[[i] for i in range(1,3 if len(calls)==2 else 201)]
        assert kwargs['required_groups']==[]
        ids=range(3,201) if len(calls)==2 else range(201,301)
        publish(dict(score=30,solutions=[solution([],identifier=i,score=10) for i in ids],has_more=len(calls)==2))
    monkeypatch.setattr('core.optimizer_process.run_isolated',isolated)
    page.optimization_mode.setCurrentIndex(1);page.deep_limit.setValue(100);page._solve()
    deadline=time.monotonic()+3
    while page.page_offset<2 and time.monotonic()<deadline:app.processEvents();time.sleep(.001)
    assert page.page_offset==2
    page._stop_deep_search()
    while page.worker is not None and time.monotonic()<deadline:app.processEvents();time.sleep(.001)
    wait_live(app,page.deep_dialog)
    assert page.worker is None and len(page.deep_dialog.model.rows)==1
    assert page.next_results.isEnabled() and page.deep_dialog.can_resume
    page.groups=[[{'kind':'affix','value':'changed after stopping'}]]
    page.deep_limit.setValue(200)
    if use_table_button:page.deep_dialog.stop.click()
    else:page.next_results.click()
    deadline=time.monotonic()+3
    while page.worker is not None and time.monotonic()<deadline:app.processEvents();time.sleep(.001)
    wait_live(app,page.deep_dialog)
    assert len(calls)==2 and page.page_offset==200
    assert not page.next_results.isEnabled() and not page.deep_dialog.stop.isEnabled()
    assert page.search_snapshot is not None and len(page.seen_combinations)==200
    assert '达到搜索上限' in page.deep_dialog.status.text()
    page.deep_limit.setValue(300)
    assert page.next_results.isEnabled() and page.deep_dialog.stop.isEnabled()
    if use_table_button:page.deep_dialog.stop.click()
    else:page.next_results.click()
    deadline=time.monotonic()+3
    while page.worker is not None and time.monotonic()<deadline:app.processEvents();time.sleep(.001)
    wait_live(app,page.deep_dialog)
    assert len(calls)==3 and page.page_offset==300
    assert page.search_snapshot is None and page.seen_combinations==[]
    page.deep_limit.setValue(400)
    assert not page.next_results.isEnabled() and not page.deep_dialog.stop.isEnabled()
    page.release_results();page.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
