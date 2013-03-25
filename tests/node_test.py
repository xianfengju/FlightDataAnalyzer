import mock
import numpy as np
import os
import unittest

from random import shuffle
from datetime import datetime
from interval import Inf

from analysis_engine.library import min_value
from analysis_engine.node import (
    ApproachItem,
    ApproachNode,
    Attribute,
    DerivedParameterNode,
    KeyPointValueNode, KeyPointValue,
    KeyTimeInstanceNode, KeyTimeInstance, KTI,
    FlightAttributeNode,
    FormattedNameNode,
    Node, NodeManager,
    Parameter, P,
    MultistateDerivedParameterNode, M,
    load,
    powerset,
    SectionNode, Section,
)

from hdfaccess.file import hdf_file
from hdfaccess.parameter import MappedArray

test_data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              'test_data')

class TestAbstractNode(unittest.TestCase):
    def test_node(self):
        pass

def _get_mock_params():
    param1 = mock.Mock()
    param1.name = 'PARAM1'
    param1.frequency = 2
    param1.offset = 0.5
    param1.get_aligned = mock.Mock()
    param1.get_aligned.return_value = 1
    param2 = mock.Mock()
    param2.name = 'PARAM2'
    param2.frequency = 0.5
    param2.offset = 1
    param2.get_aligned = mock.Mock()
    param2.get_aligned.return_value = 2
    return param1, param2

class TestNode(unittest.TestCase):

    def test_name(self):
        """ Splits on CamelCase and title cases
        """
        NewNode = type('Camel4CaseName', (Node,), dict(derive=lambda x:x))
        self.assertEqual(NewNode.get_name(), 'Camel 4 Case Name')
        NewNode = type('ThisIsANode', (Node,), dict(derive=lambda x:x))
        self.assertEqual(NewNode.get_name(), 'This Is A Node')
        NewNode = type('My2BNode', (Node,), dict(derive=lambda x:x))
        self.assertEqual(NewNode.get_name(), 'My 2B Node')
        NewNode = type('_1000Ft', (Node,), dict(derive=lambda x:x))
        self.assertEqual(NewNode.get_name(), '1000 Ft')
        NewNode = type('TouchdownV2Max', (Node,), dict(derive=lambda x:x))
        self.assertEqual(NewNode.get_name(), 'Touchdown V2 Max')

    def test_get_dependency_names(self):
        """ Check class names or strings return strings
        """
        class ParameterB(DerivedParameterNode):
            def derive(self):
                pass

        class KeyPointValue123(KeyPointValueNode):
            def derive(self, aa=P('Parameter A'), bb=ParameterB):
                pass

        self.assertEqual(KeyPointValue123.get_dependency_names(),
                         ['Parameter A', 'Parameter B'])

    def test_can_operate(self):
        deps = ['a', 'b', 'c']
        class NewNode(Node):
            def derive(self, aa=P('a'), bb=P('b'), cc=P('c')):
                pass
            def get_derived(self, deps):
                pass
        self.assertTrue(NewNode.can_operate(deps))
        extra_deps = deps + ['d', 'e', 'f']
        self.assertTrue(NewNode.can_operate(extra_deps))
        # shuffle them about
        shuffle(extra_deps)
        self.assertTrue(NewNode.can_operate(extra_deps))
        shuffle(extra_deps)
        self.assertTrue(NewNode.can_operate(extra_deps))
        not_enough_deps = ['b', 'c']
        self.assertFalse(NewNode.can_operate(not_enough_deps))

    def test_can_operate_with_objects_and_string_dependencies(self):
        def deriveparent(self, one=P('a')):
            pass
        Parent = type('Parent', (Node,), dict(derive=deriveparent,
                                              get_derived=lambda x:x))
        def derivenew(self, one=P('b'), two=Parent):
            pass
        NewNode = type('NewNode', (Node,), dict(derive=derivenew,
                                                get_derived=lambda x:x))

        available = ['a', 'Parent', 'b']
        self.assertTrue(NewNode.can_operate(available))

    def test_get_operational_combinations(self):
        """ NOTE: This shows a REALLY neat way to test all combinations of a
        derived Node class!
        """
        class Combo(Node):
            def derive(self, aa=P('a'), bb=P('b'), cc=P('c')):
                # we require 'a' and 'b' and 'c' is a bonus
                assert aa == 'A'
                assert bb == 'B'
                return aa, bb, cc

            def get_derived(self, params):
                pass

            @classmethod
            def can_operate(cls, available):
                return 'a' in available and 'b' in available

        options = Combo.get_operational_combinations()
        self.assertEqual(options, [('a', 'b'), ('a', 'b', 'c')])

        # get all operational options to test its derive method under
        options = Combo.get_operational_combinations()
        c = Combo()

        for args in options:
            # build ordered dependencies
            deps = []
            for param in c.get_dependency_names():
                if param in args:  # in expected combo
                    deps.append(param.upper())
                else:  # dependency not available
                    deps.append(None)
            # test derive method with this combination
            res = c.derive(*deps)
            self.assertEqual(res[:2], ('A', 'B'))

    def test_get_derived_default(self):
        param1, param2 = _get_mock_params()

        class TestNode(Node):
            def derive(self, kwarg1=param1, kwarg2=param2):
                pass

        node = TestNode()
        node.derive = mock.Mock()
        node.derive.return_value = None
        node.get_derived([param1, param2])
        self.assertFalse(param1.get_aligned.called)
        self.assertEqual(param2.get_aligned.call_args[0][0].frequency, param1.frequency)
        self.assertEqual(param2.get_aligned.call_args[0][0].offset, param1.offset)
        # check param1 is returned unchanged and param2 get_aligned is called
        # (returns '2')
        node.derive.assert_called_once_with(param1, 2)
        param1, param2 = _get_mock_params()
        param3 = FlightAttributeNode('Attr')
        node.derive = mock.Mock()
        node.derive.return_value = None
        node.get_derived([param3, param2])
        node.derive.assert_called_once_with(param3, param2)

    def test_get_derived_not_implemented(self):
        param1, param2 = _get_mock_params()

        class NotImplementedNode(Node):
            def derive(self, kwarg1=param1, kwarg2=param2):
                return NotImplemented

        not_implemented_node = NotImplementedNode()
        self.assertRaises(NotImplementedError, not_implemented_node.get_derived,
                          [param1, param2])

    def test_get_derived_unaligned(self):
        param1, param2 = _get_mock_params()

        class UnalignedNode(Node):
            align = False
            def derive(self, kwarg1=param1, kwarg2=param2):
                pass

        node = UnalignedNode()
        derived_parameter = node.get_derived([param1, param2])
        self.assertEqual(param1.method_calls, [])
        self.assertEqual(param2.method_calls, [])
        # Check that the default 1hz frequency and 0 offset are not used
        self.assertEqual(derived_parameter.frequency, 2)
        self.assertEqual(derived_parameter.offset, 0.5)

    def test_get_derived_align_to_frequency(self):
        param1, param2 = _get_mock_params()

        class AlignedToFrequencyNode(Node):
            align = True
            align_frequency = 4
            def derive(self, kwarg1=param1, kwarg2=param2):
                pass

        node = AlignedToFrequencyNode()
        node.derive = mock.Mock()
        node.derive.return_value = None
        derived_parameter = node.get_derived([param1, param2])
        self.assertEqual(param1.get_aligned.call_args[0][0].frequency, 4)
        self.assertEqual(param1.get_aligned.call_args[0][0].offset, 0.5)
        self.assertEqual(param2.get_aligned.call_args[0][0].frequency, 4)
        self.assertEqual(param2.get_aligned.call_args[0][0].offset, 0.5)
        self.assertEqual(derived_parameter.frequency, 4)
        self.assertEqual(derived_parameter.offset, 0.5)
        node.derive.assert_called_with(1, 2)

    def test_get_derived_align_to_frequency_offset(self):
        param1, param2 = _get_mock_params()

        class AlignedToFrequencyOffsetNode(Node):
            align = True
            align_frequency = 4
            align_offset = 0
            def derive(self, kwarg1=param1, kwarg2=param2):
                pass

        node = AlignedToFrequencyOffsetNode()
        node.derive = mock.Mock()
        node.derive.return_value = None
        derived_parameter = node.get_derived([param1, param2])
        self.assertEqual(param1.get_aligned.call_args[0][0].frequency, 4)
        self.assertEqual(param1.get_aligned.call_args[0][0].offset, 0)
        self.assertEqual(param2.get_aligned.call_args[0][0].frequency, 4)
        self.assertEqual(param2.get_aligned.call_args[0][0].offset, 0)
        self.assertEqual(derived_parameter.frequency, 4)
        self.assertEqual(derived_parameter.offset, 0)

    def test_save_and_load(self):
        node = Node('node', 2, 1.2)
        dest = os.path.join(test_data_path, 'node.nod')
        # save with compression
        node.save(dest)
        self.assertTrue(os.path.isfile(dest))
        # load
        res = load(dest)
        self.assertIsInstance(res, Node)
        self.assertEqual(res.frequency, 2)
        self.assertEqual(res.offset, 1.2)
        os.remove(dest)
        # save without compression
        node.save(dest, compress=False)
        self.assertTrue(os.path.isfile(dest))
        # load
        res = load(dest)
        self.assertIsInstance(res, Node)
        self.assertEqual(res.frequency, 2)
        self.assertEqual(res.offset, 1.2)
        os.remove(dest)


class TestAttribute(unittest.TestCase):

    def test___eq__(self):
        pairs = [
            (Attribute('Test', 0), Attribute('Test', 0)),
            (Attribute('Test', 'a'), Attribute('Test', 'a')),
            (Attribute('Test', []), Attribute('Test', [])),
            (Attribute('Test', {}), Attribute('Test', {})),
        ]
        for a, b in pairs:
            self.assertEqual(a, b)
            self.assertEqual(b, a)
            self.assertTrue(a == b)
            self.assertTrue(b == a)
            self.assertFalse(a != b)
            self.assertFalse(b != a)
            self.assertEqual(0, cmp(a, b))
            self.assertEqual(0, cmp(b, a))

    def test___ne__(self):
        pairs = [
            (Attribute('Test', 0), Attribute('Test', 1)),
            (Attribute('Test', 'a'), Attribute('Test', 'b')),
            (Attribute('Test', []), Attribute('Test', [1])),
            (Attribute('Test', {}), Attribute('Test', {'a': 1})),
        ]
        for a, b in pairs:
            self.assertNotEqual(a, b)
            self.assertNotEqual(b, a)
            self.assertFalse(a == b)
            self.assertFalse(b == a)
            self.assertTrue(a != b)
            self.assertTrue(b != a)
            self.assertNotEqual(0, cmp(a, b))
            self.assertNotEqual(0, cmp(b, a))

    def test___lt__(self):
        pairs = [
            (Attribute('Test', 0), Attribute('Test', 1)),
            (Attribute('Test', 'a'), Attribute('Test', 'b')),
            (Attribute('Test', [1]), Attribute('Test', [2])),
            (Attribute('Test', {'a': 1}), Attribute('Test', {'a': 2})),
        ]
        for a, b in pairs:
            self.assertLess(a, b)
            self.assertGreater(b, a)
            self.assertTrue(a < b)
            self.assertTrue(b > a)
            self.assertFalse(a > b)
            self.assertFalse(b < a)


class TestFlightAttributeNode(unittest.TestCase):
    def test_nonzero_flight_attr_node(self):
        'If no value is set, object evaluates to False - else True'
        attr = FlightAttributeNode()
        self.assertFalse(bool(attr))
        attr.value = []
        self.assertFalse(bool(attr))
        attr.value = 'something'
        self.assertTrue(bool(attr))
        attr.value = True
        self.assertTrue(bool(attr))
        attr.value = False
        self.assertFalse(bool(attr))

    def test_nonzero_attribute(self):
        'If no value is set, object evaluates to False - else True'
        attr = Attribute('Attribute')
        self.assertFalse(bool(attr))
        attr.value = []
        self.assertFalse(bool(attr))
        attr.value = 'something'
        self.assertTrue(bool(attr))
        attr.value = True
        self.assertTrue(bool(attr))
        attr.value = False
        self.assertFalse(bool(attr))

class TestNodeManager(unittest.TestCase):
    def test_operational(self):
        mock_node = mock.Mock('can_operate') # operable node
        mock_node.can_operate = mock.Mock(return_value=True)
        mock_inop = mock.Mock('can_operate') # inoperable node
        mock_inop.can_operate = mock.Mock(return_value=False)
        aci = {'n':1, 'o':2, 'p':3, 'u': None}
        afr = {'l':4, 'm':5, 'v': None}
        mgr = NodeManager(None, 10, ['a', 'b', 'c', 'x'], ['a', 'x'],
                          {'x': mock_inop, # note: derived node is not operational, but is already available in LFL - so this should return true!
                           'y': mock_node, 'z': mock_inop},
                          aci, afr)
        self.assertTrue(mgr.operational('a', []))
        self.assertTrue(mgr.operational('b', []))
        self.assertTrue(mgr.operational('c', []))
        # to ensure that if an lfl param is available, it's can_operate
        # returns True rather than calling the Derived node which may not
        # have all it's dependencies set. 'x' should return from the LFL!
        self.assertTrue(mgr.operational('x', []))
        self.assertTrue(mgr.operational('y', ['a']))
        self.assertTrue(mgr.operational('l', ['a'])) # achieved flight record
        self.assertTrue(mgr.operational('n', ['a'])) # aircraft info
        self.assertFalse(mgr.operational('v', ['a'])) # achieved flight record
        self.assertFalse(mgr.operational('u', ['a'])) # aircraft info
        self.assertFalse(mgr.operational('z', ['a', 'b']))
        self.assertEqual(mgr.keys(),
                         ['HDF Duration', 'Start Datetime'] +
                         list('abclmnopxyz'))

    def test_get_attribute(self):
        aci = {'a': 'a_value', 'b': None}
        afr = {'x': 'x_value', 'y': None}
        start_datetime = datetime.now()
        hdf_duration = 100
        mgr = NodeManager(start_datetime, hdf_duration, [], [], {}, aci, afr)
        # test aircraft info
        a = mgr.get_attribute('a')
        self.assertEqual(a.__repr__(), Attribute('a', 'a_value').__repr__())
        b = mgr.get_attribute('b')
        self.assertFalse(b)
        c = mgr.get_attribute('c')
        self.assertFalse(c)
        # test afr
        x = mgr.get_attribute('x')
        self.assertEqual(x.__repr__(), Attribute('x', 'x_value').__repr__())
        y = mgr.get_attribute('y')
        self.assertFalse(y)
        z = mgr.get_attribute('z')
        self.assertFalse(z)
        start_datetime_node = mgr.get_attribute('Start Datetime')
        self.assertEqual(start_datetime_node.name, 'Start Datetime')
        self.assertEqual(start_datetime_node.value, start_datetime)
        hdf_duration_node = mgr.get_attribute('HDF Duration')
        self.assertEqual(hdf_duration_node.name, 'HDF Duration')
        self.assertEqual(hdf_duration_node.value, hdf_duration)

    def test_get_start_datetime(self):
        dt = datetime(2020,12,25)
        mgr = NodeManager(dt, 10, [],[],{},{},{})
        self.assertTrue('Start Datetime' in mgr.keys())
        start_dt = mgr.get_attribute('Start Datetime')
        self.assertEqual(start_dt.name, 'Start Datetime')
        self.assertEqual(start_dt.value, dt)
        self.assertTrue(mgr.operational('Start Datetime', []))


class TestPowerset(unittest.TestCase):
    def test_powerset(self):
        deps = ['aaa',  'bbb', 'ccc']
        res = list(powerset(deps))
        expected = [(),
                    ('aaa',),
                    ('bbb',),
                    ('ccc',),
                    ('aaa', 'bbb'),
                    ('aaa', 'ccc'),
                    ('bbb', 'ccc'),
                    ('aaa', 'bbb', 'ccc')]
        self.assertEqual(res, expected)


class TestApproachNode(unittest.TestCase):
    def test__check_type(self):
        approach = ApproachNode()
        approach._check_type('LANDING')
        self.assertRaises(ValueError, approach._check_type, 'LIFTOFF')

    def test_create_approach(self):
        approach = ApproachNode()
        approach.create_approach('TOUCH_AND_GO', slice(5, 15))
        self.assertEqual(approach, [ApproachItem('TOUCH_AND_GO', slice(5,15))])
        airport = {'id': 2475}
        runway = {'id': 8429}
        gs_est = slice(22,24)
        loc_est = slice(23,24)
        ils_freq = 124
        turnoff = 29
        lowest_lat = 10.2
        lowest_lon = 42.1
        lowest_hdg = 15
        approach.create_approach(
            'LANDING', slice(20, 30), airport=airport, runway=runway,
            gs_est=gs_est, loc_est=loc_est, ils_freq=ils_freq, turnoff=turnoff,
            lowest_lat=lowest_lat, lowest_lon=lowest_lon, lowest_hdg=lowest_hdg,
        )
        self.assertEqual(len(approach), 2)
        self.assertEqual(approach[1], ApproachItem(
            'LANDING', slice(20, 30), airport=airport, runway=runway,
            gs_est=gs_est, loc_est=loc_est, ils_freq=ils_freq, turnoff=turnoff,
            lowest_lat=lowest_lat, lowest_lon=lowest_lon,
            lowest_hdg=lowest_hdg,))
        # index is not within the approach slice
        self.assertRaises(ValueError, approach.create_approach, 40, 'LANDING',
                          slice(20, 30))

    def test_get_methods(self):
        go_around = ApproachItem('GO_AROUND', slice(15, 25))
        touch_and_go = ApproachItem('TOUCH_AND_GO', slice(5, 15))
        landing = ApproachItem('LANDING', slice(25, 35))
        approach = ApproachNode(items=[go_around, touch_and_go, landing])
        self.assertEqual(approach.get(), approach)
        self.assertEqual(approach.get_first(), touch_and_go)
        self.assertEqual(approach.get_last(), landing)
        go_arounds = approach.get(_type='GO_AROUND')
        self.assertEqual(go_arounds, ApproachNode(items=[go_around]))
        within_slice = approach.get(within_slice=slice(9,21),
                                    within_use='any')
        self.assertEqual(within_slice,
                         ApproachNode(items=[go_around, touch_and_go]))
        empty = approach.get(_type='LANDING', within_slice=slice(9,21))
        self.assertEqual(empty, ApproachNode())
        none = approach.get_first(_type='LANDING', within_slice=slice(9,21))
        self.assertEqual(none, None)

    def test_get_aligned(self):
        airport = {'id': 1}
        runway = {'id': 2}
        approach = ApproachNode(name='One', frequency=2, offset=0.75, items=[
            ApproachItem('GO_AROUND', slice(5, 15)),
            ApproachItem('TOUCH_AND_GO', slice(15, 25), airport=airport,
                         runway=runway, ils_freq=110, gs_est=slice(17, 22),
                         loc_est=slice(18,23)),
            ApproachItem('LANDING', slice(25, 35), turnoff=40),
        ])
        align_to = Node('Two', frequency=1, offset=0.25)
        aligned = approach.get_aligned(align_to)
        result = ApproachNode(
            name='One', frequency=align_to.frequency,
            offset=align_to.offset, items=[
                ApproachItem('GO_AROUND', slice(3, 8)),
                ApproachItem('TOUCH_AND_GO', slice(8, 13), airport=airport,
                         runway=runway, ils_freq=110, gs_est=slice(9, 12),
                         loc_est=slice(10,12)),
                ApproachItem('LANDING', slice(13, 18), turnoff=20.5),
            ])
        self.assertEqual(aligned, result)

    def test_get_aligned_empty(self):
        approach = ApproachNode(frequency=2, offset=0.75)
        align_to = ApproachNode(frequency=1, offset=0.25)
        aligned = approach.get_aligned(align_to)
        self.assertEqual(align_to, aligned)


class TestSection(unittest.TestCase):
    #Q: Move this to a new interval_test.py?
    def test_section_slice_creation(self):
        # allow None to None
        self.assertEqual(Section(None, None).slice, slice(None))
        # ensures slices have the contraint values of start to stop+1
        self.assertEqual(Section(2, 4, name='sect').name, 'sect')
        self.assertEqual(Section(2, 4).slice, slice(2, 5)) 
        self.assertEqual(Section(2.3, 4.2).lower_bound, 2.3)
        self.assertEqual(Section(2.3, 4.2).upper_bound, 4.2) 
        self.assertEqual(Section(2.3, 4.2).slice, slice(3, 5)) 
        self.assertEqual(Section(2.9, 4.9).slice, slice(3, 5))
        self.assertEqual(Section(1.9, 4.2).slice, slice(2, 5))
        # ensure sections created from a slice have correct start/stop pos
        self.assertEqual(Section(_slice=slice(1, 3)).slice, slice(1, 3))
        # note: 2.2 is actually a upper_bound of 1.2 rounded up to 2.
        self.assertEqual(Section(_slice=slice(0.9, 2.2)).slice, slice(1, 2))
        self.assertEqual(Section(_slice=slice(0.9, 2.2)).lower_bound, 0.9)
        self.assertAlmostEqual(Section(_slice=slice(0.9, 2.2)).upper_bound, 1.2)
        
        # can't define lower_bound AND a slice
        self.assertRaises(TypeError, Section, 2, _slice=slice(2, 3))
        
        # cannot create a section which stops before it starts!!
        #NOTE: Although this is allowed in slice() creation
        self.assertRaises(TypeError, Section, 4, 2)
        self.assertRaises(TypeError, Section, 1.9, 0.9)
        self.assertRaises(TypeError, _slice=slice(1.9, 2.2))
                          
        # cannot use step different from 1 or None
        self.assertRaises(NotImplementedError, Section, _slice=slice(1, 10, -1))
        self.assertRaises(NotImplementedError, Section, _slice=slice(1, 10, 2))
        
    def test_slice_closed_and_open_ended(self):
        # default is closed lower and upper, like so:
        self.assertEqual(Section(2, 5, closed=True).slice, slice(2, 6))
        # don't include the lower bound
        self.assertEqual(Section(2, 5, lower_closed=False).slice, slice(3, 6))
        # don't include the upper bound
        self.assertEqual(Section(2, 5, upper_closed=False).slice, slice(2, 5))
        # exclude 2 and 5 from slice
        self.assertEqual(Section(2, 5, closed=False).slice, slice(3, 5))
        self.assertEqual(Section(2, 3, lower_closed=False).slice, slice(3, 4))
        
    def test_position__in__(self):
        self.assertTrue(12 in Section(None, 13))
        self.assertTrue(12 in Section(10, 12))
        self.assertTrue(12.2 in Section(10, None))
        self.assertFalse(12.2 in Section(None, 12))
        self.assertFalse(12 in Section(14, None))
        
    def test_section_overlaps(self):
        self.assertTrue(Section(10, 12).overlaps(Section(11, 13)))
        self.assertTrue(Section(None, 12).overlaps(Section(11, 13)))
        self.assertTrue(Section(10, None).overlaps(Section(11, 13)))
        self.assertTrue(Section(10, 12).overlaps(Section(None, 13)))
        self.assertTrue(Section(10, 12).overlaps(Section(11, None)))
        self.assertFalse(Section(10, 12).overlaps(Section(5, 6)))
        self.assertFalse(Section(10, 12).overlaps(Section(None, 6)))
        self.assertFalse(Section(10, 12).overlaps(Section(13, None)))
        
    def test_size_and_duration(self):
        self.assertEqual(Section(10, 20).size, 10)
        self.assertEqual(Section(None, 20).size, Inf)
        self.assertEqual(Section(10, None).size, Inf)
        self.assertEqual(Section(10, 20).duration(2), 5)
        self.assertEqual(Section(10.9, 12.1), 1.2)
        self.assertEqual(Section(10.9, 12.1).duration(1), 1.2)
        self.assertEqual(Section(10.9, 12.1).duration(4), 4.8)
        self.assertEqual(Section(10, None).duration, Inf)


class TestSectionNode(unittest.TestCase):
    def setUp(self):
        class ExampleSectionNode(SectionNode):
            def derive(self, a=P('a',[], 2, 0.4)):
                pass
            def get_derived(self):
                pass
        self.section_node_class = ExampleSectionNode

    def test_get_aligned(self):
        '''
        TODO: Test offset alignment.
        '''
        section_node = self.section_node_class(frequency=1, offset=0.5)
        section_node.create_section(2, 4)
        section_node.create_section(5, 7)
        param = Parameter('p', frequency=0.5, offset=0.1)
        aligned_node = section_node.get_aligned(param)
        self.assertEqual(aligned_node.frequency, param.frequency)
        self.assertEqual(aligned_node.offset, param.offset)
        self.assertEqual(len(aligned_node), 2)
        self.assertEqual(aligned_node[0].lower_bound, 1.2)
        self.assertEqual(aligned_node[0].upper_bound, 2.2)
        self.assertEqual(aligned_node[0].slice, slice(2, 3, None))
        self.assertEqual(aligned_node[0].name, 'Example Section Node')
        self.assertEqual(aligned_node[1].lower_bound, 2.7)
        self.assertEqual(aligned_node[1].upper_bound, 3.7)
        self.assertEqual(aligned_node[1].slice, slice(3, 4, None))
        self.assertEqual(aligned_node[1].name, 'Example Section Node')

    def test_get_aligned_with_slice_start_as_none(self):
        section_node = self.section_node_class(frequency=1, offset=0.5)
        section_node.create_section(None, 4)
        section_node.create_section(5, None)
        param = Parameter('p', frequency=0.5, offset=0.1)
        aligned_node = section_node.get_aligned(param)
        self.assertEqual(aligned_node[0].lower_bound, -Inf)  # WHY DOES THIS FAIL??
        self.assertEqual(aligned_node[0].upper_bound, 2.2)
        self.assertEqual(aligned_node[0].slice, slice(None, 3, None))
        self.assertEqual(aligned_node[0].name, 'Example Section Node')
        self.assertEqual(aligned_node[1].lower_bound, 2.7)
        self.assertEqual(aligned_node[1].upper_bound, Inf)
        self.assertEqual(aligned_node[1].slice, slice(3, None, None))
        self.assertEqual(aligned_node[1].name, 'Example Section Node')
    
    def test_items(self):
        items = [Section(_slice=slice(0,10), name='a')]
        section_node = self.section_node_class(frequency=1, offset=0.5,
                                               items=items)
        self.assertEqual(section_node, SectionNode(items))

    def test_get_slices(self):
        section_node = self.section_node_class(frequency=1, offset=0.5)
        slices = section_node.get_slices()
        self.assertEqual(slices, [])
        section_node.create_section(2, 4)
        section_node.create_section(5, 7)
        slices = section_node.get_slices()
        self.assertEqual(slices, [slice(2, 5), slice(5, 8)])

    def test_logical_and(self):
        ldg = SectionNode(items=[
            Section(lower_bound=9.5, upper_bound=15, name='Landing')])
        app_ldg = SectionNode(items=[
            Section(lower_bound=None, upper_bound=15, name='Approach and Landing')])
        
        expected_app = SectionNode(items=[Section(lower_bound=9.5, upper_bound=15)])
        resulting_app = ldg & app_ldg
        self.assertEqual(resulting_app, expected_app)
        # check result is of Section type (therefore having a slice attribute)
        self.assertIsInstance(resulting_app[0], Section)
        self.assertTrue(hasattr(resulting_app[0], 'slice'))
        
        # test using SectionNode and Section in AND
        res = SectionNode(items=[Section(5, 10)]) & Section(7, 12)
        self.assertEqual(res, SectionNode(items=[Section(7, 10)]))
        
    def test_logical_or(self):
        ldg = SectionNode(items=[
            Section(lower_bound=9.5, upper_bound=15, name='Landing')])
        app_ldg = SectionNode(items=[
            Section(lower_bound=None, upper_bound=12, name='Approach and Landing'),
            Section(lower_bound=18, upper_bound=20, name='Approach and Landing'),
        ])
        
        expected_app = SectionNode(items=[
            Section(lower_bound=None, upper_bound=15),
            Section(lower_bound=18, upper_bound=20),
        ])
        resulting_app = ldg | app_ldg
        self.assertEqual(resulting_app, expected_app)
    
    def test_logical_xor(self):
        ldg = SectionNode(items=[
            Section(lower_bound=9.5, upper_bound=15, name='Landing')]) # 1st
        app_ldg = SectionNode(items=[
            Section(lower_bound=None, upper_bound=12, name='Approach and Landing'), # 2nd
            Section(lower_bound=18, upper_bound=20, name='Approach and Landing'), # 3rd
        ])
        
        expected_app = SectionNode(items=[
            Section(lower_bound=None, upper_bound=9.5, closed=False),  # Excluding -Inf and 9.5 from 2nd start
            Section(lower_bound=12, upper_bound=15, lower_closed=False), # Excluding 12 from 2nd end
            Section(lower_bound=18, upper_bound=20),
        ])
        resulting_app = ldg ^ app_ldg
        self.assertEqual(str(resulting_app), str(expected_app))
        self.assertEqual(resulting_app, expected_app)


class TestFormattedNameNode(unittest.TestCase):
    def setUp(self):
        class ExampleNameFormatNode(FormattedNameNode):
            def derive(self, a=P('a',[], 2, 0.4)):
                pass
            def get_derived(self):
                pass
        self.formatted_name_node = ExampleNameFormatNode()

        class Speed(FormattedNameNode):
            NAME_FORMAT = '%(speed)s'
            NAME_VALUES = {'speed' : ['Slowest', 'Fast', 'Warp 10']}
            def derive(self, *args, **kwargs):
                pass

        self.speed_class = Speed


    def test_no_name_uses_node_name(self):
        names = self.formatted_name_node.names()
        self.assertEqual(names, ["Example Name Format Node"])
        #Q: Should this include name of node?
        name = self.formatted_name_node.format_name()
        self.assertEqual(name, "Example Name Format Node")


    def test_names(self):
        """
        Using all RETURNS options, apply NAME_FORMAT to obtain a complete
        list of KPV names this class will create.
        """
        class SpeedInPhaseAtAltitude(FormattedNameNode):
            NAME_FORMAT = 'Speed in %(phase)s at %(altitude)d ft'
            NAME_VALUES = {'altitude': range(100, 701, 300),
                           'phase': ['ascent', 'descent']}
            def derive(self, *args, **kwargs):
                pass
        formatted_name_node = SpeedInPhaseAtAltitude()
        names = formatted_name_node.names()

        self.assertEqual(names, ['Speed in ascent at 100 ft',
                                 'Speed in ascent at 400 ft',
                                 'Speed in ascent at 700 ft',
                                 'Speed in descent at 100 ft',
                                 'Speed in descent at 400 ft',
                                 'Speed in descent at 700 ft',])

    def test__validate_name(self):
        """ Ensures that created names have a validated option
        """
        class Speed(FormattedNameNode):
            NAME_FORMAT = 'Speed in %(phase)s at %(altitude)d ft'
            NAME_VALUES = {'altitude' : range(100, 1000),
                           'phase' : ['ascent', 'descent']}
            def derive(self, *args, **kwargs):
                pass
        formatted_name_node = Speed()
        self.assertTrue(
            formatted_name_node._validate_name('Speed in ascent at 500 ft'))
        self.assertTrue(
            formatted_name_node._validate_name('Speed in descent at 900 ft'))
        self.assertTrue(
            formatted_name_node._validate_name('Speed in descent at 100 ft'))
        self.assertFalse(
            formatted_name_node._validate_name('Speed in ascent at -10 ft'))

    def test_get(self):
        class AltitudeWhenDescending(FormattedNameNode):
            NAME_FORMAT = '%(altitude)d Ft Descending'
            NAME_VALUES = {'altitude' : range(50, 100),}
            def derive(self, *args, **kwargs):
                pass
        alt_desc = AltitudeWhenDescending(items=[
            KeyTimeInstance(100, '50 Ft Descending')])
        desc_50ft = alt_desc.get(name='50 Ft Descending')
        self.assertEqual(desc_50ft[0], alt_desc[0])
        # Raises ValueError when name is not valid.
        self.assertRaises(ValueError, alt_desc.get, name='200 Ft Descending')

    def test_get_first(self):
        # Test empty Node first.
        empty_kti_node = KeyTimeInstanceNode()
        self.assertEqual(empty_kti_node.get_last(), None)
        kti_node = self.speed_class(items=[KeyTimeInstance(12, 'Slowest'),
                                           KeyTimeInstance(342, 'Slowest'),
                                           KeyTimeInstance(2, 'Slowest'),
                                           KeyTimeInstance(50, 'Fast')])

        # no slice
        kti1 = kti_node.get_first()
        self.assertEqual(kti1.index, 2)
        # within a slice
        kti2 = kti_node.get_first(within_slice=slice(15,100))
        self.assertEqual(kti2.index, 50)
        # with a particular name
        kti3 = kti_node.get_first(name='Slowest')
        self.assertEqual(kti3.index, 2)
        kti4 = kti_node.get_first(name='Fast')
        self.assertEqual(kti4.index, 50)
        # named within a slice
        kti5 = kti_node.get_first(within_slice=slice(10,400), name='Slowest')
        self.assertEqual(kti5.index, 12)
        # does not exist
        kti6 = kti_node.get_first(name='Warp 10')
        self.assertEqual(kti6, None)
        kti7 = kti_node.get_first(within_slice=slice(500,600))
        self.assertEqual(kti7, None)

    def test_get_last(self):
        # Test empty Node first.
        empty_kti_node = KeyTimeInstanceNode()
        self.assertEqual(empty_kti_node.get_last(), None)
        kti_node = self.speed_class(items=[KeyTimeInstance(12, 'Slowest'),
                                           KeyTimeInstance(342, 'Slowest'),
                                           KeyTimeInstance(2, 'Slowest'),
                                           KeyTimeInstance(50, 'Fast')])
        # no slice
        kti1 = kti_node.get_last()
        self.assertEqual(kti1.index, 342)
        # within a slice
        kti2 = kti_node.get_last(within_slice=slice(15,100))
        self.assertEqual(kti2.index, 50)
        # with a particular name
        kti3 = kti_node.get_last(name='Slowest')
        self.assertEqual(kti3.index, 342)
        kti4 = kti_node.get_last(name='Fast')
        self.assertEqual(kti4.index, 50)
        # named within a slice
        kti5 = kti_node.get_last(within_slice=slice(10,400), name='Slowest')
        self.assertEqual(kti5.index, 342)
        # does not exist
        kti6 = kti_node.get_last(name='Warp 10')
        self.assertEqual(kti6, None)
        kti7 = kti_node.get_last(within_slice=slice(500,600))
        self.assertEqual(kti7, None)

    def test_get_named(self):
        kti_node = self.speed_class(items=[KeyTimeInstance(12, 'Slowest'),
                                           KeyTimeInstance(342, 'Slowest'),
                                           KeyTimeInstance(2, 'Slowest'),
                                           KeyTimeInstance(50, 'Fast')])
        kti_node_returned1 = kti_node.get(name='Slowest')
        self.assertEqual(kti_node_returned1,
                         [KeyTimeInstance(12, 'Slowest'),
                          KeyTimeInstance(342, 'Slowest'),
                          KeyTimeInstance(2, 'Slowest'),])
        kti_node_returned2 = kti_node.get(name='Fast')
        self.assertEqual(kti_node_returned2, [KeyTimeInstance(50, 'Fast')])
        # named within a slice
        kti_node_returned3 = kti_node.get(name='Slowest',
                                          within_slice=slice(10,400))
        self.assertEqual(kti_node_returned3,
                         [KeyTimeInstance(12, 'Slowest'),
                          KeyTimeInstance(342, 'Slowest')])
        # does not exist
        kti_node_returned4 = kti_node.get(name='Warp 10')
        self.assertEqual(kti_node_returned4, [])
        kti_node_returned5 = kti_node.get(name='Slowest',
                                          within_slice=slice(500,600))
        self.assertEqual(kti_node_returned5, [])


    def test_get_ordered_by_index(self):
        kti_node = self.speed_class(items=[KeyTimeInstance(12, 'Slowest'),
                                           KeyTimeInstance(342, 'Slowest'),
                                           KeyTimeInstance(2, 'Slowest'),
                                           KeyTimeInstance(50, 'Fast')])

        # no slice
        kti_node_returned1 = kti_node.get_ordered_by_index()
        self.assertTrue(isinstance(kti_node_returned1, self.speed_class))
        self.assertEqual(kti_node.name, kti_node_returned1.name)
        self.assertEqual(kti_node.frequency, kti_node_returned1.frequency)
        self.assertEqual(kti_node.offset, kti_node_returned1.offset)
        self.assertEqual(kti_node_returned1,
                         [KeyTimeInstance(2, 'Slowest'),
                          KeyTimeInstance(12, 'Slowest'),
                          KeyTimeInstance(50, 'Fast'),
                          KeyTimeInstance(342, 'Slowest')])
        # within a slice
        kti_node_returned2 = kti_node.get_ordered_by_index(
            within_slice=slice(15,100))
        self.assertEqual(kti_node_returned2, [KeyTimeInstance(50, 'Fast')])
        # with a particular name
        kti_node_returned3 = kti_node.get_ordered_by_index(name='Slowest')
        self.assertEqual(kti_node_returned3,
                         [KeyTimeInstance(2, 'Slowest'),
                          KeyTimeInstance(12, 'Slowest'),
                          KeyTimeInstance(342, 'Slowest')])
        kti_node_returned4 = kti_node.get_ordered_by_index(name='Fast')
        self.assertEqual(kti_node_returned4, [KeyTimeInstance(50, 'Fast')])
        # named within a slice
        kti_node_returned5 = kti_node.get_ordered_by_index(
            within_slice=slice(10,400), name='Slowest')
        self.assertEqual(kti_node_returned5,
                         [KeyTimeInstance(12, 'Slowest'),
                          KeyTimeInstance(342, 'Slowest')])
        # does not exist
        kti_node_returned6 = kti_node.get_ordered_by_index(name='Warp 10')
        self.assertEqual(kti_node_returned6, [])
        kti_node_returned7 = kti_node.get_ordered_by_index(
            within_slice=slice(500,600))
        self.assertEqual(kti_node_returned7, [])

    def test_get_next(self):
        kti_node = self.speed_class(items=[KeyTimeInstance(12, 'Slowest'),
                                           KeyTimeInstance(342, 'Slowest'),
                                           KeyTimeInstance(2, 'Slowest'),
                                           KeyTimeInstance(50, 'Fast')])
        next_kti = kti_node.get_next(35)
        self.assertEqual(next_kti, KeyTimeInstance(50, 'Fast'))
        next_kti = kti_node.get_next(35, name="Slowest")
        self.assertEqual(next_kti, KeyTimeInstance(342, 'Slowest'))
        next_kti = kti_node.get_next(1, within_slice=slice(10,20))
        self.assertEqual(next_kti, KeyTimeInstance(12, 'Slowest'))
        next_kti = kti_node.get_next(65, name="Fast")
        self.assertEqual(next_kti, None)
        next_kti = kti_node.get_next(1, frequency=0.25)
        self.assertEqual(next_kti, KeyTimeInstance(12, 'Slowest'))

    def test_get_previous(self):
        kti_node = self.speed_class(items=[KeyTimeInstance(12, 'Slowest'),
                                           KeyTimeInstance(342, 'Slowest'),
                                           KeyTimeInstance(2, 'Slowest'),
                                           KeyTimeInstance(50, 'Fast')])
        previous_kti = kti_node.get_previous(56)
        self.assertEqual(previous_kti, KeyTimeInstance(50, 'Fast'))
        previous_kti = kti_node.get_previous(410, name="Slowest")
        self.assertEqual(previous_kti, KeyTimeInstance(342, 'Slowest'))
        previous_kti = kti_node.get_previous(60, within_slice=slice(10,20))
        self.assertEqual(previous_kti, KeyTimeInstance(12, 'Slowest'))
        previous_kti = kti_node.get_previous(25, name="Fast")
        self.assertEqual(previous_kti, None)
        previous_kti = kti_node.get_previous(40, frequency=4)
        self.assertEqual(previous_kti, KeyTimeInstance(2, 'Slowest'))

    def test_initial_items_storage(self):
        node = FormattedNameNode(['a', 'b', 'c'])
        self.assertEqual(list(node), ['a', 'b', 'c'])
        node = FormattedNameNode(('a', 'b', 'c'))
        self.assertEqual(list(node), ['a', 'b', 'c'])
        node = FormattedNameNode(items=['a', 'b', 'c'])
        self.assertEqual(list(node), ['a', 'b', 'c'])


class TestKeyPointValueNode(unittest.TestCase):

    def setUp(self):
        class KPV(KeyPointValueNode):
            def derive(self, a=P('a',[], 2, 0.4)):
                pass
        self.knode = KPV(frequency=2, offset=0.4)

        class Speed(KeyPointValueNode):
            NAME_FORMAT = '%(speed)s'
            NAME_VALUES = {'speed' : ['Slowest', 'Fast', 'Warp 10']}
            def derive(self, *args, **kwargs):
                pass

        self.speed_class = Speed

    def test_create_kpv(self):
        """ Tests name format substitution and return type
        """
        class Speed(KeyPointValueNode):
            NAME_FORMAT = 'Speed in %(phase)s at %(altitude)dft'
            NAME_VALUES = {'phase': ['ascent', 'descent'],
                           'altitude': [1000, 1500],}
            def derive(self, *args, **kwargs):
                pass

        knode = Speed(frequency=2, offset=0.4)
        self.assertEqual(knode.frequency, 2)
        self.assertEqual(knode.offset, 0.4)
        # use keyword arguments
        spd_kpv = knode.create_kpv(10, 12.5, phase='descent', altitude=1000.0)
        self.assertTrue(isinstance(knode[0], KeyPointValue))
        self.assertTrue(isinstance(spd_kpv, KeyPointValue))
        self.assertEqual(spd_kpv.index, 10)
        self.assertEqual(spd_kpv.value, 12.5)
        self.assertEqual(spd_kpv.name, 'Speed in descent at 1000ft')
        # use dictionary argument
        # and check interpolation value 'ignored' is indeed ignored
        spd_kpv2 = knode.create_kpv(10, 12.5, dict(phase='ascent',
                                                   altitude=1500.0,
                                                   ignored='excuseme'))
        self.assertEqual(spd_kpv2.name, 'Speed in ascent at 1500ft')
        # None index
        self.assertEqual(knode.create_kpv(None, 'b'), None)
        # missing interpolation value "altitude"
        self.assertRaises(KeyError, knode.create_kpv, 1, 2,
                          dict(phase='ascent'))
        # wrong type raises TypeError
        self.assertRaises(TypeError, knode.create_kpv, 2, '3',
                          phase='', altitude='')
        # None index -- now logs a WARNING and does not raise an error
        knode.create_kpv(None, 'b')
        self.assertTrue('b' not in knode)  ## this test isn't quite right...!


    def test_create_kpvs_at_ktis(self):
        knode = self.knode
        param = P('Param', np.ma.arange(10))
        # value_at_index will interpolate masked values.
        param.array[3:7] = np.ma.masked
        ktis = KTI(items=[KeyTimeInstance(i, 'a') for i in range(0,10,2)])
        knode.create_kpvs_at_ktis(param.array, ktis)
        self.assertEqual(list(knode),
                         [KeyPointValue(index=0, value=0, name='Kpv'),
                          KeyPointValue(index=2, value=2, name='Kpv'),
                          KeyPointValue(index=8, value=8, name='Kpv')])

    def test_create_kpvs_at_ktis_suppressed_zeros(self):
        knode = self.knode
        param = P('Param', np.ma.array([0]*5+[7]*5))
        # value_at_index will interpolate masked values.
        param.array[3:7] = np.ma.masked
        ktis = KTI(items=[KeyTimeInstance(i, 'a') for i in range(0,10,2)])
        knode.create_kpvs_at_ktis(param.array, ktis, suppress_zeros=True)
        self.assertEqual(list(knode),
                         [KeyPointValue(index=8, value=7, name='Kpv')])

    def test_create_kpvs_within_slices(self):
        knode = self.knode
        function = mock.Mock()
        return_values = [(10, 15), (22, 27)]
        def side_effect(*args, **kwargs):
            return return_values.pop()
        function.side_effect = side_effect

        # When slicing our data the result may not have integer endpoints.
        slices = [slice(1,10.7), slice(15.15, 25)]

        array = np.ma.arange(10)
        knode.create_kpvs_within_slices(array, slices, function)
        self.assertEqual(list(knode),
                         [KeyPointValue(index=22, value=27, name='Kpv'),
                          KeyPointValue(index=10, value=15, name='Kpv')])

    def test_create_kpv_from_slices(self):
        knode = self.knode
        slices = [slice(20, 30), slice(5, 10)]
        array = np.ma.arange(30) + 15
        array.mask = True
        knode.create_kpv_from_slices(array, slices, min_value)
        self.assertEqual(knode, [])
        array.mask = False
        knode.create_kpv_from_slices(array, slices, min_value)
        self.assertEqual(list(knode),
                         [KeyPointValue(index=5, value=20, name='Kpv')])
        self.assertRaises(ValueError, knode.create_kpv_from_slices,
                          array, [slice(5, 10, 3)], min_value)

    def test_create_kpv_outside_slices(self):
        knode = self.knode
        function = mock.Mock()
        return_values = [(12, 15)]
        def side_effect(*args, **kwargs):
            return return_values.pop()
        function.side_effect = side_effect
        slices = [slice(1,10), slice(15, 25)]
        array = np.ma.arange(10)
        knode.create_kpv_outside_slices(array, slices, function)

        # See test_create_kpvs_within_slices - we need to handle non-integer endpoints.

        self.assertEqual(list(knode),
                         [KeyPointValue(index=12, value=15, name='Kpv')])

    def test_create_kpvs_where_state(self):
        knode = self.knode
        array = np.ma.array([0.0] * 20, dtype=float)
        array[5:8] = 1.0
        array[11:17] = 1.0
        mapping = {0: 'Down', 1: 'Up'}
        param = P('Disc', MappedArray(array, values_mapping=mapping))
        knode.create_kpvs_where_state('Up', param.array, param.hz)
        self.assertEqual(list(knode),
                         [KeyPointValue(index=5, value=3, name='Kpv'),
                          KeyPointValue(index=11, value=6, name='Kpv')])

    def test_create_kpvs_where_state_excluding_front_edge(self):
        knode = self.knode
        array = np.ma.array([0.0] * 20, dtype=float)
        array[:8] = 1.0
        array[11:17] = 1.0
        mapping = {0: 'Down', 1: 'Up'}
        param = P('Disc', MappedArray(array, values_mapping=mapping))
        knode.create_kpvs_where_state('Up', param.array, param.hz, exclude_leading_edge=True)
        self.assertEqual(list(knode),
                         [KeyPointValue(index=11, value=6, name='Kpv')])

    def test_create_kpvs_where_state_different_frequency(self):
        knode = self.knode
        array = np.ma.array([0.0] * 20, dtype=float)
        array[5:8] = 1.0  # shorter than 3 secs duration - ignored.
        array[11:17] = 1.0
        mapping = {0: 'Down', 1: 'Up'}
        param = P('Disc', MappedArray(array, values_mapping=mapping),
                  frequency=2.0)
        knode.create_kpvs_where_state('Up', param.array, param.hz,
                                      min_duration=3)
        self.assertEqual(list(knode),
                         [KeyPointValue(index=11, value=3, name='Kpv')])

    def test_get_aligned(self):
        '''
        TODO: Test offset alignment.
        '''
        class Speed(KeyPointValueNode):
            NAME_FORMAT = 'Speed at %(altitude)dft'
            NAME_VALUES = {'altitude': [1000, 1500],}
            def derive(self, *args, **kwargs):
                pass
        knode = Speed(frequency=2, offset=0.4)
        param = Parameter('p', frequency=0.5, offset=1.5)
        knode.create_kpv(10, 12.5, altitude=1000)
        knode.create_kpv(24, 12.5, altitude=1000)
        aligned_node = knode.get_aligned(param)
        self.assertEqual(aligned_node.frequency, param.frequency)
        self.assertEqual(aligned_node.offset, param.offset)
        self.assertEqual(aligned_node,
                         [KeyPointValue(index=1.95, value=12.5, name='Speed at 1000ft'),
                          KeyPointValue(index=5.45, value=12.5, name='Speed at 1000ft')])

    def test_get_min(self):
        # Test empty Node first.
        empty_kpv_node = KeyPointValueNode()
        self.assertEqual(empty_kpv_node.get_min(), None)
        kpv_node = self.speed_class(items=[KeyPointValue(12, 30, 'Slowest'),
                                           KeyPointValue(342, 60, 'Slowest'),
                                           KeyPointValue(2, 14, 'Slowest'),
                                           KeyPointValue(50, 369, 'Fast')])
        # no slice
        kpv1 = kpv_node.get_min()
        self.assertEqual(kpv1.value, 14)
        # within a slice
        kpv2 = kpv_node.get_min(within_slice=slice(15,100))
        self.assertEqual(kpv2.value, 369)
        # with a particular name
        kpv3 = kpv_node.get_min(name='Slowest')
        self.assertEqual(kpv3.value, 14)
        kpv4 = kpv_node.get_min(name='Fast')
        self.assertEqual(kpv4.value, 369)
        # named within a slice
        kpv5 = kpv_node.get_min(within_slice=slice(10,400), name='Slowest')
        self.assertEqual(kpv5.value, 30)
        # does not exist
        kpv6 = kpv_node.get_min(name='Warp 10')
        self.assertEqual(kpv6, None)
        kpv7 = kpv_node.get_min(within_slice=slice(500,600))
        self.assertEqual(kpv7, None)

    def test_get_max(self):
        # Test empty Node first.
        empty_kpv_node = KeyPointValueNode()
        self.assertEqual(empty_kpv_node.get_max(), None)
        kpv_node = self.speed_class(items=[KeyPointValue(12, 30, 'Slowest'),
                                           KeyPointValue(342, 60, 'Slowest'),
                                           KeyPointValue(2, 14, 'Slowest'),
                                           KeyPointValue(50, 369, 'Fast')])

        # no slice
        kpv1 = kpv_node.get_max()
        self.assertEqual(kpv1.value, 369)
        # within a slice
        kpv2 = kpv_node.get_max(within_slice=slice(15,100))
        self.assertEqual(kpv2.value, 369)
        # with a particular name
        kpv3 = kpv_node.get_max(name='Slowest')
        self.assertEqual(kpv3.value, 60)
        kpv4 = kpv_node.get_max(name='Fast')
        self.assertEqual(kpv4.value, 369)
        # named within a slice
        kpv5 = kpv_node.get_max(within_slice=slice(10,400), name='Slowest')
        self.assertEqual(kpv5.value, 60)
        # does not exist
        kpv6 = kpv_node.get_max(name='Warp 10')
        self.assertEqual(kpv6, None)
        kpv7 = kpv_node.get_max(within_slice=slice(500,600))
        self.assertEqual(kpv7, None)

    def test_get_ordered_by_value(self):
        kpv_node = self.speed_class(items=[KeyPointValue(12, 30, 'Slowest'),
                                           KeyPointValue(342, 60, 'Slowest'),
                                           KeyPointValue(2, 14, 'Slowest'),
                                           KeyPointValue(50, 369, 'Fast')])

        # no slice
        kpv_node_returned1 = kpv_node.get_ordered_by_value()
        self.assertTrue(isinstance(kpv_node_returned1, KeyPointValueNode))
        self.assertEqual(kpv_node.name, kpv_node_returned1.name)
        self.assertEqual(kpv_node.frequency, kpv_node_returned1.frequency)
        self.assertEqual(kpv_node.offset, kpv_node_returned1.offset)
        self.assertEqual(kpv_node_returned1,
                         [KeyPointValue(2, 14, 'Slowest'),
                          KeyPointValue(12, 30, 'Slowest'),
                          KeyPointValue(342, 60, 'Slowest'),
                          KeyPointValue(50, 369, 'Fast')])
        # within a slice
        kpv_node_returned2 = kpv_node.get_ordered_by_value(
            within_slice=slice(15,100))
        self.assertEqual(kpv_node_returned2, [KeyPointValue(50, 369, 'Fast')])
        # with a particular name
        kpv_node_returned3 = kpv_node.get_ordered_by_value(name='Slowest')
        self.assertEqual(kpv_node_returned3,
                         [KeyPointValue(2, 14, 'Slowest'),
                          KeyPointValue(12, 30, 'Slowest'),
                          KeyPointValue(342, 60, 'Slowest')])
        kpv_node_returned4 = kpv_node.get_ordered_by_value(name='Fast')
        self.assertEqual(kpv_node_returned4, [KeyPointValue(50, 369, 'Fast')])
        # named within a slice
        kpv_node_returned5 = kpv_node.get_ordered_by_value(
            within_slice=slice(10,400), name='Slowest')
        self.assertEqual(kpv_node_returned5,
                         [KeyPointValue(12, 30, 'Slowest'),
                          KeyPointValue(342, 60, 'Slowest')])
        # does not exist
        kpv_node_returned6 = kpv_node.get_ordered_by_value(name='Warp 10')
        self.assertEqual(kpv_node_returned6, [])
        kpv_node_returned7 = kpv_node.get_ordered_by_value(
            within_slice=slice(500,600))
        self.assertEqual(kpv_node_returned7, [])

    def test__get_slices(self):
        section_node = SectionNode(items=[Section(10, 20),
                                          Section(30, 40)])
        slices = KeyPointValueNode._get_slices(section_node)
        self.assertEqual(slices, section_node.get_slices())
        input_slices = [slice(10, 20), slice(10, 20)]
        self.assertEqual(KeyPointValueNode._get_slices(input_slices),
                         input_slices)

    def test__get_slice_edges(self):
        section_node = SectionNode(items=[Section(9.9, 20.2),
                                          Section(30.1, 39.85)])
        slices = KeyPointValueNode._get_slices(section_node)
        self.assertEqual(slices, section_node.get_slices())
        input_slices = [slice(9.9, 20.2), slice(30.1, 39.85)]
        self.assertEqual(KeyPointValueNode._get_slices(input_slices),
                         input_slices)



class TestKeyTimeInstanceNode(unittest.TestCase):
    def setUp(self):
        class KTI(KeyTimeInstanceNode):
            def derive(self, a=P('a')):
                pass
        self.kti = KTI(frequency=2, offset=0.4)

    def test_create_kti(self):
        kti = self.kti
        #KTI = type('MyKti', (KeyTimeInstanceNode,), dict(derive=lambda x:x,
                                                         #dependencies=['a']))
        #params = {'a':Parameter('a',[], 2, 0.4)}
        #kti = KTI(frequency=2, offset=0.4)
        kti.create_kti(12)
        self.assertEqual(list(kti), [KeyTimeInstance(index=12, name='Kti')])

        # NAME_FORMAT
        class Flap(KeyTimeInstanceNode):
            NAME_FORMAT = 'Flap %(setting)d'
            NAME_VALUES = {'setting': [10, 25, 35]}
            def derive(self, a=P('a')):
                pass
        kti = Flap()
        kti.create_kti(24, setting=10)
        kti.create_kti(35, {'setting':25})
        self.assertEqual(list(kti), [KeyTimeInstance(index=24, name='Flap 10'),
                                     KeyTimeInstance(index=35, name='Flap 25'),])
        # None index
        self.assertRaises(ValueError, kti.create_kti, None)

    def test_create_ktis_at_edges_inside_phases(self):
        kti=self.kti
        test_array = np.ma.array([0,1,0,1,0,1,0,1,0])
        test_phase = SectionNode(items=[Section(None, 2),
                                        Section(5, None)])
        kti.create_ktis_at_edges(test_array, phase=test_phase)
        self.assertEqual(kti,[KeyTimeInstance(index=0.5, name='Kti'),
                              KeyTimeInstance(index=6.5, name='Kti')])


    def test_create_ktis_at_edges_replace_values(self):
        class EngineNumber(KeyTimeInstanceNode):
            NAME_FORMAT = 'Eng (%(number)d)'
            NAME_VALUES = {'number': [1, 2]}
        kti = EngineNumber()
        test_param = np.ma.array([0, 0, 0, 1, 1, 1, 0, 0, 0])
        kti.create_ktis_at_edges(test_param, direction='all_edges',
                                 replace_values={'number': 1})
        self.assertEqual(kti,[KeyTimeInstance(index=2.5, name='Eng (1)'),
                              KeyTimeInstance(index=5.5, name='Eng (1)')])

    def test_create_ktis_at_edges_either(self):
        kti=self.kti
        test_param = np.ma.array([0,0,0,1,1,1,0,0,0])
        kti.create_ktis_at_edges(test_param, direction='all_edges')
        self.assertEqual(kti,[KeyTimeInstance(index=2.5, name='Kti'),
                              KeyTimeInstance(index=5.5, name='Kti')])

    def test_create_ktis_at_edges_rising(self):
        kti=self.kti
        test_param = np.ma.array([0,0,0,1,1,1,0,0,0])
        kti.create_ktis_at_edges(test_param)
        self.assertEqual(kti,[KeyTimeInstance(index=2.5, name='Kti')])

    def test_create_ktis_at_edges_falling(self):
        kti=self.kti
        test_param = np.ma.array([0,1,1,0,0,0,-1,-1,0])
        kti.create_ktis_at_edges(test_param, direction='falling_edges')
        self.assertEqual(kti,[KeyTimeInstance(index=2.5, name='Kti'),
                              KeyTimeInstance(index=5.5, name='Kti')])

    def test_create_ktis_at_edges_fails(self):
        kti=self.kti
        test_param = np.ma.array([0])
        self.assertRaises(ValueError, kti.create_ktis_at_edges, test_param,
                          direction='sideways')

    def test_create_ktis_on_state_change_borders_entering(self):
        # The KTIs should not be created on borders of the data (start and end)
        kti = self.kti
        test_param = MappedArray([1, 1, 0, 0, 0, 0, 1],
                                 values_mapping={0: 'Off', 1: 'On'})
        kti.create_ktis_on_state_change('On', test_param,
                                        change='entering')
        self.assertEqual(kti, [KeyTimeInstance(index=5.5, name='Kti')])

    def test_create_ktis_on_state_change_borders_leaving(self):
        # The KTIs should not be created on borders of the data (start and end)
        kti = self.kti
        test_param = MappedArray([1, 1, 0, 0, 0, 0, 1],
                                 values_mapping={0: 'Off', 1: 'On'})
        kti.create_ktis_on_state_change('On', test_param,
                                        change='leaving')
        self.assertEqual(kti, [KeyTimeInstance(index=1.5, name='Kti')])

    def test_create_ktis_on_state_change_entering(self):
        kti = self.kti
        test_param = MappedArray([0, 1, 1, 0, 0, 0, 0, 1, 0],
                                 values_mapping={0: 'Off', 1: 'On'})
        kti.create_ktis_on_state_change('On', test_param, change='entering')
        self.assertEqual(kti, [KeyTimeInstance(index=0.5, name='Kti'),
                               KeyTimeInstance(index=6.5, name='Kti')])

    def test_create_ktis_on_state_change_leaving(self):
        kti = self.kti
        test_param = MappedArray([0, 1, 1, 0, 0, 0, 0, 1, 0],
                                 values_mapping={0: 'Off', 1: 'On'})
        kti.create_ktis_on_state_change('On', test_param, change='leaving')
        self.assertEqual(kti, [KeyTimeInstance(index=2.5, name='Kti'),
                               KeyTimeInstance(index=7.5, name='Kti')])

    def test_create_ktis_on_state_change_entering_and_leaving(self):
        kti = self.kti
        test_param = MappedArray([0, 1, 1, 0, 0, 0, 0, 1, 0],
                                 values_mapping={0: 'Off', 1: 'On'})
        kti.create_ktis_on_state_change('On', test_param,
                                        change='entering_and_leaving')
        self.assertEqual(kti, [KeyTimeInstance(index=0.5, name='Kti'),
                               KeyTimeInstance(index=2.5, name='Kti'),
                               KeyTimeInstance(index=6.5, name='Kti'),
                               KeyTimeInstance(index=7.5, name='Kti')])

    def test_get_aligned(self):
        '''
        TODO: Test offset alignment.
        '''
        kti = self.kti
        #KTI = type('MyKti', (KeyTimeInstanceNode,), dict(derive=lambda x:x,
                                                         #dependencies=['a']))
        #params = {'a':Parameter('a',[], 2, 0.4)}
        #kti = KTI(frequency=2, offset=0.4)
        kti.create_kti(16)
        kti.create_kti(18)
        param = Parameter('p', frequency=0.25, offset=2)
        aligned_kti = kti.get_aligned(param)
        self.assertEqual(aligned_kti,
                         [KeyTimeInstance(index=1.6, name='Kti'),
                          KeyTimeInstance(index=1.85, name='Kti')])


class TestDerivedParameterNode(unittest.TestCase):
    def setUp(self):
        class ExampleDerivedParameterNode(DerivedParameterNode):
            def derive(self, alt_std=P('Altitude STD'),
                       pitch=P('Pitch')):
                pass
        class UnalignedDerivedParameterNode(DerivedParameterNode):
            align_to_first_dependency = False
            def derive(self, alt_std=P('Altitude STD'),
                       pitch=P('Pitch')):
                pass
        self.derived_class = ExampleDerivedParameterNode
        self.unaligned_class = UnalignedDerivedParameterNode

    @unittest.skip('Not Implemented')
    def test_frequency(self):
        self.assertTrue(False)
        # assert that Frequency MUST be set

        # assert that Derived masked array is of the correct length given the frequency
        # given a sample set of data for 10 seconds, assert that a 2 Hz param has len 20


        # Q: Have an aceessor on the DerivedParameter.get_result() which asserts the correct length of data returned.

    @unittest.skip('Not Implemented')
    def test_offset(self):
        self.assertTrue(False)
        # assert that offset MUST be set

    def test_force_masked_array(self):
        '''
        Ensures that we create a masked array if one was not provided.
        '''
        p1 = Parameter('Parameter')
        p2 = Parameter('Parameter', array=[1, 2, 3])
        p3 = Parameter('Parameter', array=np.ma.MaskedArray([1, 2, 3]))
        self.assertIsInstance(p1.array, np.ma.MaskedArray)
        self.assertIsInstance(p2.array, np.ma.MaskedArray)
        self.assertIsInstance(p3.array, np.ma.MaskedArray)
        self.assertRaises(TypeError, Parameter, ('Parameter', ['a', 'b', 'c']))

    def test_get_derived_aligns(self):
        '''
        Tests get_derived returns a Parameter object rather than a
        DerivedParameterNode aligned to the frequency and offset of the first
        parameter passed to get_derived()
        '''
        param1 = Parameter('Altitude STD', frequency=1, offset=0)
        param2 = Parameter('Pitch', frequency=0.5, offset=1)
        # use first available param's freq and offset.
        derive_param = self.derived_class(frequency=param1.frequency,
                                          offset=param1.offset)
        result = derive_param.get_derived([param1, param2])
        self.assertIsInstance(result, DerivedParameterNode)
        self.assertEqual(result.frequency, param1.frequency)
        self.assertEqual(result.offset, param1.offset)

    def test_get_derived_unaligned(self):
        """
        Set the class attribute align_to_first_dependency = False
        """
        param1 = Parameter('Altitude STD', frequency=1, offset=0)
        param2 = Parameter('Pitch', frequency=0.5, offset=1)
        unaligned_param = self.unaligned_class(frequency=param1.frequency,
                                               offset=param1.offset)
        result = unaligned_param.get_derived([param1, param2])
        self.assertIsInstance(result, DerivedParameterNode)
        self.assertEqual(result.frequency, unaligned_param.frequency)
        self.assertEqual(result.offset, unaligned_param.offset)

    def test_get_derived_discrete_align(self):
        '''
        Ensure that interpolations do not occur.
        '''
        class Flap(MultistateDerivedParameterNode):
            values_mapping = {1: 'one', 2: 'two', 3: 'three'}

        master_param = Parameter(array=np.ma.array([5,6,7]),
                                 frequency=1, offset=0.4)

        slave_flap = Flap(array=np.ma.array([1,2,3]),
                          frequency=1, offset=0)
        res = slave_flap.get_aligned(master_param)
        # note it has not interpolated to 1.4, 2.4, 3.4 forward
        self.assertEqual(list(res.array.raw), [1, 2, np.ma.masked])

    def test_parameter_at(self):
        # using a plain range as the parameter array, the results are equal to
        # the index used to get the value (cool)
        spd = Parameter('Airspeed', np.ma.array(range(20)), 2, 0.75)
        self.assertEqual(spd.at(0.75), 0) # min val possible to return
        self.assertEqual(spd.at(1.75), 1*2) # one second in (*2Hz)
        self.assertEqual(spd.at(2.5), 1.75*2) # interpolates
        self.assertEqual(spd.at(9.75), 9*2) # max val without extrapolation
        self.assertEqual(spd.at(0), 0) # Extrapolation at bottom end
        self.assertEqual(spd.at(11), 19) # Extrapolation at top end

    @mock.patch('analysis_engine.node.slices_above')
    def test_slices_above(self, slices_above):
        '''
        Ensure slices_above is called with the expected arguments.
        '''
        array = np.ma.arange(10)
        slices_above.return_value = (array, [slice(0,10)])
        param = DerivedParameterNode('Param', array=array)
        slices = param.slices_above(5)
        slices_above.assert_called_once_with(array, 5)
        self.assertEqual(slices, slices_above.return_value[1])

    @mock.patch('analysis_engine.node.slices_below')
    def test_slices_below(self, slices_below):
        '''
        Ensure slices_below is called with the expected arguments.
        '''
        array = np.ma.arange(10)
        slices_below.return_value = (array, [slice(0,10)])
        param = DerivedParameterNode('Param', array=array)
        slices = param.slices_below(5)
        slices_below.assert_called_once_with(array, 5)
        self.assertEqual(slices, slices_below.return_value[1])

    @mock.patch('analysis_engine.node.slices_between')
    def test_slices_between(self, slices_between):
        '''
        Ensure slices_between is called with the expected arguments.
        '''
        array = np.ma.arange(10)
        slices_between.return_value = (array, [slice(0, 10)])
        param = DerivedParameterNode('Param', array=array)
        slices = param.slices_between(5, 15)
        slices_between.assert_called_once_with(array, 5, 15)
        self.assertEqual(slices, slices_between.return_value[1])

    @mock.patch('analysis_engine.node.slices_from_to')
    def test_slices_from_to(self, slices_from_to):
        '''
        Ensure slices_from_to is called with the expected arguments.
        '''
        array = np.ma.arange(10)
        slices_from_to.return_value = (array, [slice(0, 10)])
        param = DerivedParameterNode('Param', array=array)
        slices = param.slices_from_to(5, 15)
        slices_from_to.assert_called_once_with(array, 5, 15)
        self.assertEqual(slices, slices_from_to.return_value[1])

    def test_slices_to_touchdown_basic(self):
        heights = np.ma.arange(100,-10,-10)
        heights[:-1] -= 10
        alt_aal = P('Altitude AAL', heights)
        tdwns = KTI(items=[KeyTimeInstance(name='Touchdown', index=9.5)])
        result = alt_aal.slices_to_kti(75, tdwns)
        expected = [slice(1.5, 9.5)]
        self.assertEqual(result, expected)

    def test_slices_to_touchdown_early(self):
        heights = np.ma.arange(100,-10,-10)
        heights[:-1] -= 10
        alt_aal = P('Altitude AAL', heights)
        tdwns = KTI(items=[KeyTimeInstance(name='Touchdown', index=6.7)])
        result = alt_aal.slices_to_kti(75, tdwns)
        expected = [slice(1.5,6.7)]
        self.assertEqual(result, expected)

    def test_slices_to_touchdown_outside_range(self):
        heights = np.ma.arange(100,-10,-10)
        heights[:-1] -= 10
        alt_aal = P('Altitude AAL',heights)
        tdwns = KTI(items=[KeyTimeInstance(name='Touchdown', index=-2)])
        result = alt_aal.slices_to_kti(75, tdwns)
        expected = []
        self.assertEqual(result, expected)

    def test_save_and_load_node(self):
        node = P('Altitude AAL', np.ma.array([0,1,2,3], mask=[0,1,1,0]),
              frequency=2, offset=0.123, data_type='Signed')
        dest = os.path.join(test_data_path, 'altitude.node')
        node.save(dest)
        self.assertTrue(os.path.isfile(dest))
        # load
        res = load(dest)
        self.assertIsInstance(res, DerivedParameterNode)
        self.assertEqual(res.frequency, 2)
        self.assertEqual(res.offset, 0.123)
        self.assertEqual(list(res.array.data), [0,1,2,3])
        self.assertEqual(list(res.array.mask), [0,1,1,0])
        os.remove(dest)
        # check large file size
        node.array = np.ma.arange(5000)
        node.dump(dest)
        from utilities.filesystem_tools import pretty_size
        print pretty_size(os.path.getsize(dest))
        self.assertLess(os.path.getsize(dest), 10000)
        os.remove(dest)

        node.dump(dest, compress=False)
        print pretty_size(os.path.getsize(dest))
        self.assertGreater(os.path.getsize(dest), 20000)
        os.remove(dest)



class TestMultistateDerivedParameterNode(unittest.TestCase):
    def setUp(self):
        self.hdf_path = os.path.join(test_data_path, 'test_node.hdf')

    def tearDown(self):
        if os.path.isfile(self.hdf_path):
            os.remove(self.hdf_path)

    def test_init(self):
        values_mapping = {1: 'one', 2: 'two', 3: 'three'}

        # init with MaskedArray
        array = np.ma.MaskedArray([1, 2, 3])
        p = M('Test Node', array, values_mapping=values_mapping)
        self.assertEqual(p.array[0], 'one')
        self.assertEqual(p.array.raw[0], 1)

        # init with MappedArray
        array = MappedArray([1, 2, 3], values_mapping=values_mapping)
        p = M('Test Node', array, values_mapping=values_mapping)
        self.assertEqual(p.array[0], 'one')
        self.assertEqual(p.array.raw[0], 1)

        # init with list of strings
        array = ['one', 'two', 'three']
        p = M('Test Node', array, values_mapping=values_mapping)
        self.assertEqual(p.array[0], 'one')
        self.assertEqual(p.array.raw[0], 1)

    def test_setattr_array(self):
        values_mapping = {1: 'one', 2: 'two', 3: 'three'}

        # init with MaskedArray
        array = np.ma.MaskedArray([1, 2, 3])
        p = M('Test Node', array, values_mapping=values_mapping)
        self.assertEqual(p.array[0], 'one')
        self.assertEqual(p.array.raw[0], 1)

        # overwrite the array
        array = np.ma.MaskedArray([3, 2, 1])
        p.array = array
        self.assertEqual(p.array[0], 'three')
        self.assertEqual(p.array.raw[0], 3)

        # overwrite the mapping
        p.values_mapping = {1: 'ein', 2: 'zwei', 3: 'drei'}
        self.assertEqual(p.array[0], 'drei')
        self.assertEqual(p.array.raw[0], 3)

        # create with float array which are actually integers
        array = np.ma.array([1., 2.5,  # note: 2.5 will be rounded to 2.0
                             3., 0.], dtype=float)
        import analysis_engine.node as n
        temp = n.multistate_string_to_integer
        n.multistate_string_to_integer = mock.Mock()
        m = M(values_mapping=values_mapping)
        m.array = array
        self.assertEqual(m.array.data.dtype, int)
        self.assertFalse(n.multistate_string_to_integer.called)
        n.multistate_string_to_integer = temp

    def test_settattr_string_array(self):
        mapping = {0:'zero', 1:'one', 2:'two', 3:'three'}
        multi_p = MultistateDerivedParameterNode('multi', values_mapping=mapping)
        input_array = np.ma.array(['one', 'two']*5, mask=[1,0,0,0,0,0,0,0,0,1], dtype=object)
        input_array.data[-1] = 'not_mapped' # masked values will be filled
        # here's the call to __setattr__:
        multi_p.array = input_array

        # test converted fine
        self.assertEqual(multi_p.array.raw.dtype, int)
        self.assertEqual(list(multi_p.array.raw[:4]),
                         [np.ma.masked, 2, 1, 2])
        self.assertEqual(list(multi_p.array[:4]),
                         [np.ma.masked, 'two', 'one', 'two'])
        # check original array left untouched
        self.assertEqual(input_array[2], 'one')

        # create values where no mapping exists and expect a keyerror
        self.assertRaises(ValueError, multi_p.__setattr__,
                          'array', np.ma.array(['zonk', 'two']*2, mask=[1,0,0,0]))


    def test_saving_to_hdf(self):
        # created mapped array
        mapping = {0:'zero', 2:'two', 3:'three'}
        array = np.ma.array(range(5)+range(5), mask=[1,1,1,0,0,0,0,0,1,1])
        multi_p = MultistateDerivedParameterNode('multi', array, values_mapping=mapping)

        multi_p.array[0] = 'three'


        #multi_p.array =

        # save array to hdf and close
        with hdf_file(self.hdf_path, create=True) as hdf1:
            hdf1['multi'] = multi_p

        # check hdf has mapping and integer values stored
        with hdf_file(self.hdf_path) as hdf:
            saved = hdf['multi']
            self.assertEqual(list(np.ma.filled(saved.array, 999)),
                             [  3, 999, 999,   3,   4,   0,   1,   2, 999, 999])
            self.assertEqual(saved.array.data.dtype, np.int)


if __name__ == '__main__':
    unittest.main()
