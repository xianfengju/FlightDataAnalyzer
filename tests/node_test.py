try:
    import unittest2 as unittest  # py2.6
except ImportError:
    import unittest

#import mock

from random import shuffle

from analysis.node import (DerivedParameterNode, KeyPointValue, 
                           KeyPointValueNode, Node, NodeManager)

class TestAbstractNode(unittest.TestCase):
    
    def test_node(self):
        pass
    

class TestNode(unittest.TestCase):
    
    def test_name(self):
        """ Splits on CamelCase and title cases
        """
        NewNode = type('Camel4CaseName', (Node,), dict(derive=lambda x:x))
        node = NewNode()
        self.assertEqual(node.get_name(), 'Camel4 Case Name')
        NewNode = type('ThisIsANode', (Node,), dict(derive=lambda x:x))
        self.assertEqual(NewNode.get_name(), 'This Is A Node')
        NewNode = type('My2BNode', (Node,), dict(derive=lambda x:x))
        self.assertEqual(NewNode.get_name(), 'My2B Node')
        NewNode.name = 'MACH'
        self.assertEqual(NewNode.get_name(), 'MACH')

    def test_get_dependency_names(self):
        """ Check class names or strings return strings
        """            
        class RateOfClimb(DerivedParameterNode):
            def derive(self):
                pass
        
        class RateOfDescentHigh(KeyPointValueNode):
            dependencies = ['Rate Of Descent', RateOfClimb]
            # Minimum period of a descent for testing against thresholds (reduces number of KPVs computed in turbulence)
            DESCENT_MIN_DURATION = 10
            
            def derive(self):
                pass
            
        rodh = RateOfDescentHigh()
        self.assertEqual(rodh.get_dependency_names(), 
                         ['Rate Of Descent', 'Rate Of Climb'])
        
    
    
        
    def test_can_operate(self):
        deps = ['a', 'b', 'c']
        NewNode = type('NewNode', (Node,), dict(derive=lambda x:x, dependencies=deps))
        node = NewNode()
        self.assertTrue(node.can_operate(deps))
        extra_deps = deps + ['d', 'e', 'f']
        self.assertTrue(node.can_operate(extra_deps))
        # shuffle them about
        shuffle(extra_deps)
        self.assertTrue(node.can_operate(extra_deps))
        shuffle(extra_deps)
        self.assertTrue(node.can_operate(extra_deps))
        not_enough_deps = ['b', 'c']
        self.assertFalse(node.can_operate(not_enough_deps))
        
    def test_can_operate_with_objects_and_string_dependencies(self):
        Parent = type('Parent', (Node,), dict(derive=lambda x:x, dependencies=['a']))
        parent = Parent()
        NewNode = type('NewNode', (Node,), dict(derive=lambda x:x, dependencies=['b', Parent]))
        node = NewNode()        
        available = ['a', 'Parent', 'b']
        self.assertTrue(node.can_operate(available))
        
    def test_get_operational_combinations(self):
        """ NOTE: This shows a REALLY neat way to test all combinations of a
        derived Node class!
        """
        class Combo(Node):
            dependencies = ['a', 'b', 'c']
            def derive(self, params): 
                # we require 'a' and 'b' and 'c' is a bonus
                return params['a'], params['b'], params.get('c')
            
            @classmethod
            def can_operate(cls, available):
                if 'a' in available and 'b' in available:
                    return True
                else:
                    return False
        
        options = Combo.get_operational_combinations()
        self.assertEqual(options, [('a', 'b'), ('a', 'b', 'c')])
        
        # define sample data for all the dependencies
        deps = {'a': 'aa',
                'b': 'bb',
                'c': 'cc', }
        # get all operational options to test its derive method under
        options = Combo.get_operational_combinations()
        c = Combo()
        for args in options:
            # build params dict
            params = {arg: deps[arg] for arg in args} #py2.7
            # test derive method with this combination
            res = c.derive(params)
            self.assertEqual(res[:2], ('aa', 'bb'))
                
                        
class TestNodeManager(unittest.TestCase):
    def test_operational(self):
        mock_node = mock.Mock()
        mock_node.returns = True
        mock_inop = mock.Mock()
        mock_inop.returns = False # inoperable node
        mgr = NodeManager(['a', 'b', 'c'], ['a', 'x'], 
                          {'x': mock_node, 'y': mock_node, 'z': mock_inop})
        self.assertTrue(mgr.operational('a', []))
        self.assertTrue(mgr.operational('b', []))
        self.assertTrue(mgr.operational('c', []))
        self.assertTrue(mgr.operational('x', []))
        self.assertTrue(mgr.operational('y', ['a']))
        self.assertFalse(mgr.operational('z', ['a', 'b']))
        

class TestKeyPointValueNode(unittest.TestCase):
    
    def test_create_kpv(self):
        """ Tests name format substitution and return type
        """
        KPV = type('kpv', (KeyPointValueNode,), dict(derive=lambda x:x))
        knode = KPV()
        knode.NAME_FORMAT = 'Speed in %(phase)s at %(altitude)dft'
        knode.RETURN_OPTIONS = {'phase':['ascent', 'descent'],
                                'altitude':[1000,1500],
                                }
        # use keyword arguments
        spd_kpv = knode.create_kpv(10, 12.5, phase='descent', altitude=1000.0)
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
        # missing interpolation value "altitude"
        self.assertRaises(KeyError, knode.create_kpv, 1, 2,
                          dict(phase='ascent'))
        # wrong type raises TypeError
        self.assertRaises(TypeError, knode.create_kpv, 2, '3', 
                          phase='', altitude='')
        
    
    def test_generate_kpv_name_list(self):
        """ Using all RETURNS options, apply NAME_FORMAT to obtain a complete
        list of KPV names this class will create.
        """
        KPV = type('kpv', (KeyPointValueNode,), dict(derive=lambda x:x))
        knode = KPV()
        knode.NAME_FORMAT = 'Speed in %(phase)s at %(altitude)d ft'
        knode.RETURN_OPTIONS = {'altitude' : range(100, 701, 300),'phase' : ['ascent', 'descent']}
        kpv_names = knode.kpv_names()
        
        self.assertEqual(kpv_names, ['Speed in ascent at 100 ft',
                                     'Speed in ascent at 400 ft',
                                     'Speed in ascent at 700 ft',
                                     'Speed in descent at 100 ft',
                                     'Speed in descent at 400 ft',
                                     'Speed in descent at 700 ft',
                                     ])
        
    def test_validate_name(self):
        """ Ensures that created names have a validated option
        """
        KPV = type('kpv', (KeyPointValueNode,), dict(derive=lambda x:x))
        knode = KPV()
        knode.NAME_FORMAT = 'Speed in %(phase)s at %(altitude)d ft'
        knode.RETURN_OPTIONS = {'altitude' : range(100,1000,100),
                                'phase' : ['ascent', 'descent']}
        self.assertTrue(knode._validate_name('Speed in ascent at 500 ft'))
        self.assertTrue(knode._validate_name('Speed in descent at 900 ft'))
        self.assertTrue(knode._validate_name('Speed in descent at 100 ft'))
        self.assertRaises(ValueError, knode._validate_name, 'Speed in ascent at -10 ft')
    
        
    ##def test_kpv_names_exist_on_db(self):
        ###urr, this probably shouldn't be here!
        ##pass
    
    
    
class TestDerivedParameterode(unittest.TestCase):
    def test_frequency(self):
        self.assertTrue(False)
        # assert that Frequency MUST be set
        
        # assert that Derived masked array is of the correct length given the frequency
        # given a sample set of data for 10 seconds, assert that a 2 Hz param has len 20
        
        
        # Q: Have an aceessor on the DerivedParameter.get_result() which asserts the correct length of data returned.
        
    def test_offset(self):
        self.assertTrue(False)
        # assert that offset MUST be set
        