#!/usr/bin/python3
import re
import structures_collection as collection
import resource_handler as resources
import convertation_handler as converter
import log_handler as logs
import itertools
import collections
import random
import string
import time
from copy import copy


class InputContainer:
    def __init__(self, content, metadata=None, prevent_auto=False):
        self.metadata = {}
        if metadata:
            self.metadata = metadata
        self.elements = []
        self.content = content
        self.INPUT = 'universal:input'
        self.ic_log = logs.log_object.New()
        self.create_default_icl_sectors()
        self.main_container = None
        self.config = InputContainerConfig()
        self.group_data = {}
        self.onseg_hooks = {}
        self.onseg_hook_bank = HookBank()
        self.__system_names = []
        if not prevent_auto:
            self.start_auto_segmentation()

    def start_auto_segmentation(self):
        self.add_element(InputContainerElement(self.INPUT, self.content, self))
        self.segment_into_childs(self.INPUT)

    def connect_mc(self, main_container):
        self.main_container = main_container
        self.main_container.copy_ic_config(self.config)

    def segment_into_childs(self, system_name):
        if system_name not in collection.dependency.systems:
            raise UndefinedSystem()
        for child_system in collection.dependency.systems[system_name]:
            try:
                for element in self.get_by_system_name(system_name):
                    self.segment_element(
                        element,
                        child_system,
                        collection.auto_segmentation.Handler.segment(system_name, child_system)(element.get_content())
                    )
                self.segment_into_childs(child_system)
            except collection.auto_segmentation.SegmentTemplateNotFound:
                continue

    def create_default_icl_sectors(self):
        self.ic_log.add_sector("STEMS_EXTRACTED")
        self.ic_log.add_sector("POS_EXTRACTED")

    def remove_childs_of(self, parent_id):
        for element in self.elements:
            if element.get_parent_ic_id() == parent_id:
                self.elements.remove(element)

    def get_by_ic_id(self, ic_id):
        for element in self.elements:
            if element.get_ic_id() == ic_id:
                return element
        return None

    def get_by_system_name(self, system_name):
        return [element for element in self.elements if element.get_system_name() == system_name]

    def get_by_fork_id(self, fork_id):
        return [element for element in self.elements if element.get_fork_id() == fork_id]

    def clone_within_cluster(self, element, new_group_index):
        new_element = copy(element)
        new_element.group = new_group_index
        del new_element.params
        new_element.params = copy(element.params)
        new_element.fork_id = element.get_ic_id()
        new_element.ic_id = self.generate_ic_id()
        self.elements.append(new_element)
        return self.get_by_ic_id(new_element.ic_id)

    def segment_element(self, element, child_system, c_outlines, set_group=None, set_fork_id=None, group_rate=None):
        """
        :param element: IC element to be splitted in segments
        :param child_system: child system of segments
        :param c_outlines: CharOutline objects (with attachment)
        :param set_group: group to set for all IC subelements (None by default)
        :param set_fork_id: fork_id to set for all IC subelements (None by default)
        :param group_rate: rate value given to the group
        :return: List of IC childs
        """
        parent_ic = element.get_ic_id()
        ices = []
        if set_group is not None:
            self.group_data[(parent_ic, set_group)] = {'rate': group_rate}
        elif (parent_ic, 0) not in self.group_data:
            self.group_data[(parent_ic, 0)] = {'rate': group_rate}
        element.set_cluster_length(child_system, len(c_outlines))
        for outline_object in c_outlines:
            try:
                mc_link = outline_object.get_metadata()['mc_id']
            except KeyError:
                mc_link = None
            except TypeError:
                mc_link = None
            ice = InputContainerElement(
                child_system, outline_object.get_attachment(), self, char_outline=outline_object,
                parent=parent_ic, mc_id_link=mc_link, group=set_group, fork_id=set_fork_id
            )
            ices.append(ice.get_ic_id())
            self.add_element(ice)
            if child_system in self.onseg_hooks:
                for system_hook in self.onseg_hooks[child_system]:
                    system_hook(self, ice)
        return ices

    def add_element(self, element):
        if element.get_system_name() not in self.__system_names:
            self.__system_names.append(element.get_system_name())
        self.elements.append(element)

    def nullint_for_cluster(self, parent_ic_id):
        self.elements = [
            (elem if elem.get_parent_ic_id() != parent_ic_id else elem.set_group_as_null()) for elem in self.elements
        ]

    def get_system_names(self):
        return self.__system_names

    @staticmethod
    def generate_ic_id():
        return ''.join(random.choice('abcdef' + string.digits) for _ in range(20))

    def get_all(self):
        return self.elements

    def backward_parse(self, input_container_element, scanned_system):
        if not self.main_container:
            raise MainContainerNotFound()
        kw_pairs = collection.backward_parsing.Handler.to_values(scanned_system)
        for pair in kw_pairs:
            collection.backward_parsing.Handler.get_parser(*pair)(self, self.main_container, input_container_element)
            # should it be procedure or function?

    def run_mc_analysis(self):
        if not self.main_container:
            raise MainContainerNotFound()
        for system in self.__system_names:
            if collection.auto_segmentation.Handler.is_auto(system):
                continue
            bw_to_values = collection.backward_parsing.Handler.to_values(system)
            if not bw_to_values and collection.dependency.systems[system]:
                raise SegMethodNotFound(system)
            for to_value in bw_to_values:
                se = self.get_by_system_name(system)
                lse = len(se)
                for j, element in enumerate(se):
                    if self.config.show_index:
                        print('{}/{} = {}'.format(j, lse, element.get_content()))
                    if self.config.broad_exception_mode:
                        try:
                            collection.backward_parsing.Handler.get_parser(system, to_value)(
                                element, self.main_container, self
                            )
                        except:
                            pass
                    else:
                        collection.backward_parsing.Handler.get_parser(system, to_value)(
                            element, self.main_container, self
                        )

    def add_onseg_hook(self, ext_system, onseg_hook):
        """
        add_onseg_hook procedure
        :param ext_system: system name which will refer to the hook
        :param onseg_hook: hook(-> IC Elem) which will be called by extraction of elements that belong to the ext_system
        """
        if ext_system not in self.onseg_hooks:
            self.onseg_hooks[ext_system] = []
        self.onseg_hooks[ext_system].append(onseg_hook)

    def make_apply(self, main_container_element_id, main_container, scanned_system):
        main_container_element = main_container.get_by_id(main_container_element_id)
        get_applied = main_container_element.get_applied()
        link_sentences = get_applied['links']
        actions = get_applied['actions']
        rows = self.get_by_system_name(scanned_system)
        for row in rows:
            for link_sentence in link_sentences:
                if link_sentence.check(row):
                    # get ic_id
                    if not collection.auto_segmentation.Handler.can_segment(scanned_system, main_container_element.get_type()):
                        extracted_ic_id = collection.layer_extraction.Handler.extract(
                            scanned_system, main_container_element.get_type()
                        )(row, main_container_element.get_content())
                    else:
                        # ???
                        # a request to logger can be done
                        for x in self.get_by_system_name(scanned_system):
                            if x.get_content() == main_container_element.get_content():
                                extracted_ic_id = x.get_ic_id()
                                break
                    for action in actions:
                        args = action.get_arguments()
                        if args:
                            collection.static.Handler.get_func(action.get_path())(
                                extracted_ic_id, args, action.branching_allowed()
                            )
                        else:
                            collection.static.Handler.get_func(action.get_path())(
                                extracted_ic_id,
                                branching=action.branching_allowed()
                            )
                    break


class InputContainerConfig:
    def __init__(self):
        self.param_rewrite = False
        self.gm_cycle_limit = 0
        self.debug_mode = False
        self.broad_exception_mode = False
        self.show_index = False
        self.submessages = self.Messages

    class Messages:
        cycle_limit_exceeded = False


class HookBank:
    def __init__(self):
        """
        Class which is used to hold variables and functions to use with onseg hooks
        """
        pass


class InputContainerElement:
    def __init__(
            self,
            system_name, content, input_container, char_outline=None, params=None,
            parent=None, group=None, fork_id=None, mc_id_link=None, rate_value=None
            ):
        self.system_name = system_name
        self.content = content
        self.input_container = input_container
        if not params:
            self.params = {}
        else:
            self.params = params
        self.char_outline = char_outline
        self.mc_id_link = mc_id_link
        self.ic_id = input_container.generate_ic_id()
        self.parent_ic_id = parent
        self.group = group
        self.fork_id = fork_id
        self.rate_value = rate_value
        self.clusters_length = {}
        if fork_id and not input_container.get_by_ic_id(fork_id):
            raise UnknownForkID()

    def set_parameter(self, param_name, param_value, branching=False):
        if not branching:
            self.params[param_name] = param_value
        else:
            if param_name in self.params and type(self.params[param_name]) != ParameterBranching:
                raise CannotCreateBranch(param_name)
            elif param_name in self.params:
                self.params[param_name].add_branch(param_value)
            else:
                self.params[param_name] = ParameterBranching(param_name)
                self.params[param_name].add_branch(param_value)

    def set_mc_link(self, mc_id_link):
        self.mc_id_link = mc_id_link

    def get_parameter(self, key, args=None, value=None):
        if args is None:
            args = []
        try:
            extractors = collection.auto_parameter_extraction.Handler.get_param_extractors(self.system_name, key)
            self.params[key] = extractors[0].extractor(self, args, value)
        except collection.auto_parameter_extraction.ExtractorNotFound:
            pass
        if key in self.params:
            if type(self.params[key]) != ParameterBranching:
                return self.params[key]
            else:
                return self.params[key].get_branches()[0]
        else:
            raise ParameterNotFound(key)

    def get_ic_id(self):
        return self.ic_id

    def get_parent_ic_id(self):
        return self.parent_ic_id

    def get_system_name(self):
        return self.system_name

    def get_content(self):
        return self.content

    def get_char_outline(self):
        return self.char_outline

    def is_last_in_cluster(self, system_name):
        parent_element = self.input_container.get_by_ic_id(self.get_parent_ic_id())
        p_childs = parent_element.get_childs(lambda e: e.get_system_name() == system_name)
        return self in p_childs and p_childs.index(self) == parent_element.clusters_length[system_name] - 1

    def co_follows(self, index):
        fg = self.char_outline.get_groups()[0]
        return fg.get_indices() != Temp.UNALLOCATED and fg.get_indices()[0] > index

    def set_cluster_length(self, system_name, length):
        self.clusters_length[system_name] = length

    def shift_following_co(self, shift_int):
        fg = self.char_outline.get_groups()[0]
        self.char_outline.shift_group(0, shift_int, fg.get_indices[0])

    def check_ca_matching(self, index):
        fg = self.char_outline.get_groups()[0]
        return fg.get_indices() != Temp.UNALLOCATED and index in fg.get_indices()

    def ca_for_element(self, ca_data):
        a_map = collections.namedtuple('addresses', 'action_type int_index rep_char shift')
        addresses = a_map(0, 1, 2, 3)
        ci = self.char_outline.get_int_index_in_group(0, ca_data[addresses.int_index])
        self.content[ci] = ca_data[addresses.rep_char]
        self.char_outline.ca_for_group(0, ca_data)

    def get_group(self):
        """
        :return: (Int; >0 because None should not confuse group number) number of group the element belongs to
        """
        return self.group

    def get_fork_id(self):
        return self.fork_id

    def get_rate_value(self):
        return self.rate_value

    def set_group_as_null(self):
        self.group = 0
        return self

    def get_childs(self, child_filter=lambda element: True):
        return [el for el in self.input_container.elements if el.get_parent_ic_id() == self.ic_id and child_filter(el)]


class ParameterBranching:
    def __init__(self, parameter_name):
        self.parameter_name = parameter_name
        self.__value_branches = []

    def add_branch(self, value):
        self.__value_branches.append(value)

    def get_branches(self):
        return self.__value_branches


class GroupCollection:
    def __init__(self, parent_ic_id, input_container, elements=None, spread_ci=True):
        self.group_count = 1
        self.groups = {}
        self.parent_ic_id = parent_ic_id
        self.input_container = input_container
        if elements is None:
            elements = self.input_container.get_by_ic_id(parent_ic_id).get_childs()
        none_group = [el for el in elements if el.get_group() is None]
        if none_group:
            self.groups[0] = none_group
            return
        cur_group = 0
        while True:
            found_group = [el for el in elements if el.get_group() == cur_group]
            if not found_group:
                break
            if cur_group not in self.groups:
                self.groups[cur_group] = found_group
            else:
                self.groups[cur_group] += found_group
            self.group_count = cur_group + 1
            cur_group += 1

        # self.groups[N] = Array of CharOutline
        if spread_ci:
            for group_index in self.groups:
                pos_spread = {}
                linearized_group = []
                for element in self.groups[group_index]:
                    for n, co_group in enumerate(element.get_char_outline().get_groups()):
                        psi_shortkey = (co_group.get_indices()[0], co_group.get_indices()[-1])
                        pos_spread[psi_shortkey] = element
                        pos_spread[psi_shortkey].char_outline.set_group_to_null(n)
                for k in sorted(list(pos_spread.keys())):
                    linearized_group.append(pos_spread[k])
                self.groups[group_index] = linearized_group

    def group(self, index):
        return self.groups[index]

    def itergroups(self, index_pair=False):
        def none_alias(x): return x if x is not None else 0
        if (self.parent_ic_id, 0) not in self.input_container.group_data:
            return []

        if not self.input_container.config.broad_exception_mode:
            sorted_indices = sorted(
                [x for x in range(self.group_count)],
                key=lambda index: none_alias(self.input_container.group_data[(self.parent_ic_id, index)]['rate']),
                reverse=True
            )
        else:
            try:
                sorted_indices = sorted(
                    [x for x in range(self.group_count)],
                    key=lambda index: none_alias(self.input_container.group_data[(self.parent_ic_id, index)]['rate']),
                    reverse=True
                )
            except KeyError:
                sorted_indices = [x for x in range(self.group_count)]
        if not self.groups:
            return []
        if not index_pair:
            return [self.groups[x] for x in sorted_indices]
        else:
            return [(x, self.groups[x]) for x in sorted_indices]

    def serialize(self):
        return list(itertools.chain(*[self.groups[N] for N in self.groups]))


class Container:
    def __init__(self):
        self.rows = []
        self.entities = []
        self.elements_on_id = dict()
        self.cont_log = logs.log_object.New()
        self.config = None
        for system in collection.dependency.systems:
            self.add_entity(ContainerEntity('system', system, self))

    def copy_ic_config(self, config):
        self.config = config

    def add_entity(self, entity_object):
        if entity_object not in self.entities:
            self.entities.append(entity_object)
        return entity_object

    def iter_content_reassignment(self, content_function):
        for row in self.rows:
            row.content = content_function(row.content)

    def get_class(self, identifier, await=False):
        for entity in self.entities:
            if entity.get_level() == 'class' and entity.get_identifier() == identifier:
                return entity
        if await:
            return self.add_entity(ContainerEntity('class', identifier, self))
        else:
            raise ClassEntityNotFound()

    def get_system(self, identifier):
        for entity in self.entities:
            if entity.get_level() == 'system' and entity.get_identifier() == identifier:
                return entity
        raise SystemEntityNotFound()

    def get_all(self):
        return self.rows

    def get_by_id(self, element_id):
        if element_id in self.elements_on_id:
            return self.elements_on_id[element_id]
        for row in self.rows:
            if row.id == element_id:
                self.elements_on_id[element_id] = row
                return row
        return False

    def get_by_class_name(self, class_name):
        elements = []
        for row in self.rows:
            if class_name in row.get_class_names():
                elements.append(row)

        return elements

    def foreach_in_class(self, class_name):
        def fic_decor(class_func):
            for row in self.rows:
                if class_name in row.get_class_names():
                    class_func(row)

            def wrapped(fa1, fa2):
                return class_func(fa1, fa2)

            return wrapped

        return fic_decor

    def get_by_type(self, element_type):
        elements = []
        for row in self.rows:
            if element_type == row.get_type():
                elements.append(row)

        return elements

    def iter_content_filter(self, filter_func, sort_by_length=False, sort_desc=False, system_filter=None):
        elements = []
        content_table = dict()
        i = 0

        for row in self.rows:
            if filter_func(row.get_content()) and (row.get_type() == system_filter if system_filter else True):
                elements.append(row)
                if sort_by_length:
                    if row.get_content() not in content_table:
                        content_table[row.get_content()] = []
                    content_table[row.get_content()].append(i)
                i += 1

        if sort_by_length:
            sorted_elements = []
            content_list = list(content_table.keys())
            content_list.sort(key=len, reverse=sort_desc)
            for s in content_list:
                for element_index in content_table[s]:
                    sorted_elements.append(elements[element_index])
            return sorted_elements
        return elements

    def get_elems_providing_param(self, param, input_container_element, scanned_system=None):
        aprp = []
        for row in self.rows:
            get_applied = row.get_applied()
            if not get_applied['links']:
                continue
            link_sentences = get_applied['links']
            actions = get_applied['actions']
            if not actions:
                continue
            for action in actions:
                for link_sentence in link_sentences:
                    check_results = link_sentence.check(input_container_element)
                    if param in collection.static.Handler.get_func_params(action) and check_results:
                        if scanned_system is None or scanned_system == row.get_type():
                            aprp.append(row.get_id())
                            break
        return aprp

    def add_element(self, element_type, element_content, element_id):
        if self.get_by_id(element_id):
            raise IdIsNotUnique()

        if collection.system_multirendering.Handler.is_renderable(element_type):
            rendered_elements = collection.system_multirendering.Handler.render(
                element_type, element_content, element_id
            )
            rnd_ids = []
            for rel in rendered_elements:
                self.rows.append(ContainerElement(rel.type, rel.content, rel.id, self))
                rnd_ids.append(rel.id)
            return ContainerElementCollection(rnd_ids, self)
        else:
            element = ContainerElement(element_type, element_content, element_id, self)
            self.rows.append(element)
            return self.get_by_id(element_id)

    def list_actions(self):
        return list(itertools.chain(*[element.get_actions() for element in self.rows]))


class ContainerEntity:
    def __init__(self, level, identifier, container):
        self.level = level
        self.identifier = identifier
        self.subcl_orders = []
        self.added_bhvr = 'standard'
        self.subelems_intrusion = []
        self.bw_lists = {}
        self.container = container

    def get_level(self):
        return self.level

    def get_identifier(self):
        return self.identifier

    def added_behaviour(self, pattern):
        if self.level != 'class':
            raise AddedBehaviourNotSupported()
        self.added_bhvr = pattern

    def subclasses_order(self, order_string, parent_filter=None, select_into=None, strict=False):
        if self.level != 'system':
            raise SubclassesOrderNotSupported()
        self.subcl_orders.append(
            SubclassesOrder(
                order_string, self.container, self.identifier, parent_filter, select_into, strict
            )
        )

    def subelements_intrusion(self, link_sentence, bw_list=None):
        self.subelems_intrusion.append(link_sentence)
        if bw_list is not None:
            self.bw_lists[len(self.subelems_intrusion) - 1] = bw_list

    def get_subcl_orders(self):
        return self.subcl_orders

    def get_subcl_orders_affecting_ids(self, id_names):
        found_orders = []
        for id_name in id_names:
            for order in self.subcl_orders:
                affected_ids = order.get_affected_ids()
                if id_name in affected_ids:
                    found_orders.append(order)
                else:
                    affected_classes = order.get_affected_classes()
                    for id_class in self.container.get_by_id(id_name).get_class_names():
                        if id_class in affected_classes:
                            found_orders.append(order)
                            break
        return list(set(found_orders))

    def inspect_added_behaviour(self):
        return self.added_bhvr

    # active intrusion
    def intrusion(self, class_list, bw_list=None):
        if class_list is None:
            raise IntrusionIsEmpty()
        for class_name in class_list:
            self.container.get_class(class_name, await=True).subelements_intrusion(
                LinkSentence('universal:class=(%s)' % class_name), bw_list
            )

    def get_subelems_intrusion(self):
        return self.subelems_intrusion


class BWList:
    def __init__(self, exclude_mutations=None):
        if exclude_mutations is None:
            exclude_mutations = []
        self.exclude_mutations = exclude_mutations


class SubclassesOrder:
    def __init__(self, order_string, main_container, sys_id, parent_filter=None, select_into=None, strict=True):
        self.scheme = []
        self.strict = strict
        self.main_container = main_container
        self.parent_filter = parent_filter
        self.sys_identifier = sys_id
        self.select_into = select_into
        self.begin = False
        self.end = False

        sp_string = order_string.split()
        if sp_string:
            if sp_string[0] == '|':
                self.begin = True
            if sp_string[-1] == '|':
                self.end = True
            sp_string = [x for x in sp_string if x != '|']

        for substr in sp_string:
            if substr == '?':
                self.scheme.append({
                    'type': 'pointer',
                    'subtype': 'everything'
                })
            elif substr.startswith('.'):
                self.scheme.append({
                    'type': 'pointer',
                    'subtype': 'class',
                    'value': substr[1:]
                })
            elif substr.startswith('#'):
                self.scheme.append({
                    'type': 'pointer',
                    'subtype': 'id',
                    'value': substr[1:]
                })
            elif '<' in substr or '>' in substr:
                lookbehind = ''.join([x for x in substr if x == '<'])
                lookahead = ''.join([x for x in substr if x == '>'])
                if lookbehind:
                    self.scheme.append({
                        'type': 'operator',
                        'subtype': 'lookbehind',
                        'value': 'optional' if len(lookbehind) == 2 else 'required'
                    })
                if lookahead:
                    self.scheme.append({
                        'type': 'operator',
                        'subtype': 'lookahead',
                        'value': 'optional' if len(lookahead) == 2 else 'required'
                    })
            else:
                raise MalformedSubOrder()

    def get_affected_classes(self):
        return [x['value'] for x in self.scheme if x['subtype'] == 'class']

    def get_affected_ids(self):
        return [x['value'] for x in self.scheme if x['subtype'] == 'id']

    def is_strict(self):
        return self.strict

    @staticmethod
    def name_escape(str2esc, double=False):
        str2esc_rep = {
            '*': [r'\*', r'\\*'],
            '$': [r'\$', r'\\$'],
            '^': [r'\^', r'\\^'],
            '(': [r'\(', r'\\('],
            ')': [r'\)', r'\\)']
        }
        for mr_key in str2esc_rep:
            str2esc = str2esc.replace(mr_key, str2esc_rep[mr_key][int(double)])
        return str2esc

    def create_asterisk_pattern(self, p_type, p_value, double=False):
        if not double:
            return r'\*' + ('#' if p_type == 'id' else r'\.') + self.name_escape(p_value) + r'\*'
        else:
            return r'\\*' + ('#' if p_type == 'id' else r'\\.') + self.name_escape(p_value, double=True) + r'\\*'

    @staticmethod
    def double_pattern_to_single(pattern):
        return pattern.replace('\\\\', '\\')

    def check_sequence(self, co_sequence, available_nulls):
        """
        :param co_sequence: List[List[MC element ID, CharOutline Object]]
        :param available_nulls: List; MC container elements filtered by content (Temp.NULL) & by system (sys_identifier)
        :return: Bool -> if the order matches the given sequence
        """
        # self.null_elements

        def get_operator(n):
            if n > 0:
                if self.scheme[n - 1]['type'] == 'operator' and self.scheme[n - 1]['subtype'] == 'lookahead':
                    return self.scheme[n - 1]['value']
            if n < len(self.scheme) - 1:
                if self.scheme[n + 1]['type'] == 'operator' and self.scheme[n + 1]['subtype'] == 'lookbehind':
                    return self.scheme[n + 1]['value']

        ev_groups = []
        non_ev = []
        check_regex = ''
        for j, el in enumerate(self.scheme):
            if el['type'] == 'pointer' and el['subtype'] == 'everything':
                if get_operator(j) == 'required':
                    check_regex += '((.+))'
                else:
                    check_regex += '((.*)|)'
                ev_groups.append(j)
            elif el['type'] == 'pointer':
                pointer_regex = '(' + '('
                el_name = self.create_asterisk_pattern(el['subtype'], el['value'])
                non_ev.append(el_name)
                pointer_regex += el_name
                pointer_regex += ')'
                if get_operator(j) == 'optional':
                    pointer_regex += '|'
                pointer_regex += ')'
                check_regex += pointer_regex
            else:
                continue
        non_ev_str = '|'.join(non_ev)

        check_regex = (r'^' if self.begin else '') + check_regex + (r'$' if self.end else '')

        subst_nulls = []
        for null in [(x.get_id(), x.get_class_names()) for x in available_nulls]:
            for j, el in enumerate(self.scheme):
                if el['type'] != 'pointer' or el['subtype'] not in ('class', 'id'):
                    continue
                if (el['subtype'] == 'id' and el['value'] == null[0]) or (el['subtype'] == 'class' and el['value'] in null[1]):
                    subst_nulls.append({
                        'null_ice': null,
                        'pre': [],
                        'post': []
                    })
                    if j > 0:
                        for i in range(j - 1, -1, -1):
                            if self.scheme[i]['type'] == 'pointer' and self.scheme[i]['subtype'] != 'everything':
                                subst_nulls[-1]['pre'].append(
                                    (self.scheme[i]['subtype'], self.scheme[i]['value'])
                                )
                    if j < len(self.scheme) - 1:
                        for i in range(j + 1, len(self.scheme)):
                            if self.scheme[i]['type'] == 'pointer' and self.scheme[i]['subtype'] != 'everything':
                                subst_nulls[-1]['post'].append(
                                    (self.scheme[i]['subtype'], self.scheme[i]['value'])
                                )

        cn_sequence = self.null_substitution(co_sequence, subst_nulls)
        el_masks = [
            [*['.' + x for x in self.main_container.get_by_id(elem.get_id()).get_class_names()], '#' + elem.get_id()]
            for elem in cn_sequence
        ]
        for mask_product in [''.join(['*' + y + '*' for y in x]) for x in itertools.product(*el_masks)]:
            rx_grouping = re.compile(check_regex).match(mask_product)
            if not rx_grouping:
                continue
            """
            if re.search(non_ev_str, rx_grouping.groups()[0]) or re.search(non_ev_str, rx_grouping.groups()[-1]):
                continue
            """
            return {
                "check": True,
                "nulls": subst_nulls,
                "cn_sequence": cn_sequence
            }

        return {
            "check": False,
            "nulls": subst_nulls,
            "cn_sequence": cn_sequence
        }

    @staticmethod
    def extract_ap(container_element):
        act_list = container_element.get_applied()['actions']
        param_list = [collection.static.Handler.get_func_params(x.get_path()) for x in act_list]
        return list(itertools.chain(*param_list))

    def null_substitution(self, co_sequence, subst_nulls):
        if not co_sequence:
            return []
        container = co_sequence[0].container
        sequence_params = list(itertools.chain(*[self.extract_ap(x) for x in co_sequence]))
        for null in subst_nulls:
            if not self.main_container.config.param_rewrite:
                for prm in self.extract_ap(container.get_by_id(null['null_ice'][0])):
                    if prm in sequence_params:
                        print(null)
                        continue
            insertion_made = False
            for pre_element_data in null['pre']:
                for j, element in enumerate(co_sequence):
                    element_id, element_classes = element.get_id(), element.get_class_names()
                    if element.get_content() == Temp.NULL:
                        continue
                    if pre_element_data[0] == 'id' and element_id == pre_element_data[1]:
                        co_sequence.insert(j, container.get_by_id(null['null_ice'][0]))
                        insertion_made = True
                        break
                    elif pre_element_data[0] == 'class' and pre_element_data[1] in element_classes:
                        co_sequence.insert(j, container.get_by_id(null['null_ice'][0]))
                        insertion_made = True
                        break
                if insertion_made:
                    break
            if insertion_made:
                continue
            for post_element_data in null['post']:
                insertion_made = False
                for j, element in enumerate(co_sequence):
                    element_id, element_classes = element.get_id(), element.get_class_names()
                    if element.get_content() == Temp.NULL:
                        continue
                    if post_element_data[0] == 'id' and element_id == post_element_data[1]:
                        co_sequence.insert(j, container.get_by_id(null['null_ice'][0]))
                        insertion_made = True
                        break
                    elif post_element_data[0] == 'class' and post_element_data[1] in element_classes:
                        co_sequence.insert(j, container.get_by_id(null['null_ice'][0]))
                        insertion_made = True
                        break
                if insertion_made:
                    break
        return co_sequence


class ContainerElementCollection:
    def __init__(self, id_list, mc_container):
        self.id_list = id_list
        self.mc_container = mc_container

    def __getattr__(self, name):
        def method(*args):
            ln = len(self.id_list)
            for j, elem_id in enumerate(self.id_list):
                if args:
                    result = self.mc_container.get_by_id(elem_id).__getattribute__(name)(*args)
                else:
                    result = self.mc_container.get_by_id(elem_id).__getattribute__(name)()

                if j == ln - 1:
                    if result == self.mc_container.get_by_id(elem_id):
                        return self
                    else:
                        return result

        return method


class ContainerElement:
    def __init__(self, element_type, element_content, element_id, container):
        self.type = element_type
        self.content = element_content
        self.container = container
        self.id = element_id
        self.class_names = []
        self.apply_for = []
        self.applied_ids = []
        self.mutation_links = []
        self.parameters = {}
        self.transmitter_local_index = None

    def applied(self, link_sentence, actions):
        self.apply_for = [link_sentence, actions]
        self.apply_for[0].set_transmitter(self)
        return self

    def get_actions(self):
        return self.apply_for[1]

    def add_applied(self, applied_id):
        self.applied_ids.append(applied_id)
        return self

    def add_class(self, class_name):
        if class_name not in self.class_names:
            self.class_names.append(class_name)
            self.container.add_entity(ContainerEntity('class', class_name, self.container))
            return self
        raise RepeatedClassAssignment()

    def edit_parameter(self, key, value=True):
        self.parameters[key] = value
        return self

    def set_parameter(self, key, value=True):
        if key not in self.parameters:
            self.edit_parameter(key, value)
        else:
            raise ParameterAlreadyExists()
        return self

    def get_parameter(self, key, args=None, value=None):
        if args is None:
            args = []
        try:
            extractors = collection.auto_parameter_extraction.Handler.get_param_extractors(self.type, key)
            self.parameters[key] = extractors[0](self.content, args, value)
        except collection.auto_parameter_extraction.ExtractorNotFound:
            pass
        if key in self.parameters:
            return self.parameters[key]
        else:
            raise ParameterNotFound()

    def get_id(self):
        return self.id

    def get_class_names(self):
        return self.class_names

    def get_type(self):
        return self.type

    def get_content(self):
        return self.content

    def get_clear_content(self):
        return collection.minor.Clear.remove_spec_chars(self.type, self.content)

    def append_child_type(self, child_type):
        if ':' in child_type:
            raise WrongChildType()
        self.type += ':' + child_type

    def provide_mutation_links(self, links):
        self.mutation_links += links

    def get_mutation_links(self):
        return self.mutation_links

    def get_applied(self):
        applied_object = {
            'links': [self.apply_for[0]],
            'actions': self.apply_for[1]
        }
        for class_name in self.class_names:
            for link_sentence in self.container.get_class(class_name).get_subelems_intrusion():
                applied_object['links'].append(link_sentence)

        if self.transmitter_local_index is not None:
            for e, link in enumerate(applied_object['links']):
                applied_object['links'][e].set_transmitter_local_index(self.transmitter_local_index)

        return applied_object

    def set_transmitter_local_index(self, tidx):
        self.transmitter_local_index = tidx


class LinkSentence:
    def __init__(self, link_string, transmitter=None, allow_resources=True, metadata=None):
        self.link = re.sub(r'\n|\s{2,}', ' ', link_string)
        self.transmitter = transmitter
        self.transmitter_index = None
        self.allow_resources = allow_resources
        self.metadata = metadata

    def set_transmitter(self, transmitter):
        self.transmitter = transmitter

    def set_metadata(self, metadata):
        self.metadata = metadata

    def set_transmitter_local_index(self, index):
        self.transmitter_index = index

    class BSArray:
        def __init__(self, simple_array, set_visited=None):
            """
            :param simple_array: List of IC container elements
            :param set_visited: array indices which should be marked as visited
            """
            self.bs_array = [[0, x] for x in simple_array]
            if set_visited:
                for i in set_visited:
                    self.bs_array[i][0] = 1

        def set_visited(self, index):
            self.bs_array[index][0] = 1

        def set_unvisited(self, index):
            self.bs_array[index][0] = 0

        def toggle(self, index):
            self.bs_array[index][0] = int(not bool(self.bs_array[index][0]))

    @staticmethod
    def get_elems_providing_param(param, bs_array, element, check_function):
        elems_found = []
        for j, elem in enumerate(bs_array.bs_array):
            if elem[0]:
                continue
            if not check_function(elem):
                continue
            row = elem[1]
            get_applied = row.get_applied()
            if not get_applied['links']:
                continue
            link_sentences = get_applied['links']
            actions = get_applied['actions']
            if not actions:
                continue
            for action in actions:
                for link_sentence in link_sentences:
                    check_results, element = link_sentence.check(element, bs_array, check_function)
                    if param in collection.static.Handler.get_func_params(action.get_path()) and check_results:
                        elems_found.append(j)
                        break
        return elems_found

    def check_element(self, element, param_pair, elems_set, check_function, block_converter=False):
        if type(elems_set) != self.BSArray:
            elems_set = self.BSArray(
                elems_set, set_visited=[self.transmitter_index] if self.transmitter_index else None
            )
        try:
            elems_set.set_visited(self.transmitter_index)
        except IndexError:
            pass

        if param_pair.prop == 'Sharp':
            return True, element, elems_set

        multiple_choice = []

        try:
            parameter = element.get_parameter(param_pair.key, param_pair.arguments, value=param_pair.value)
        except ParameterNotFound:
            need_elems = self.get_elems_providing_param(param_pair.key, elems_set, element, check_function)

            if need_elems:
                for index in need_elems:
                    elems_set.set_visited(index)
                    if not collection.dependency.check_transitivity(
                            element.get_system_name(), elems_set.bs_array[index][1].get_type()
                    ):
                        continue
                    for action in elems_set.bs_array[index][1].get_applied()['actions']:
                        element = collection.static.Handler.get_func(action.get_path())(element, action.get_arguments())
                parameter = element.get_parameter(param_pair.key, param_pair.arguments, value=param_pair.value)

            elif not self.allow_resources:
                parameter = resources.request_functions.Handler.get_parameter(param_pair.key, element)

            elif not block_converter:
                # is not ready yet
                parameter = None
                try:
                    multiple_choice = converter.convert_param_pair(param_pair.key, param_pair.value)
                except converter.CannotConvertSystemTypes:
                    raise CannotGetParameter(param_pair.key)

            else:
                if param_pair.operator == "!=" and param_pair.is_bool_check():
                    return True, element, elems_set
                raise CannotGetParameter(param_pair.key)

        param_set = (parameter,) if not multiple_choice else multiple_choice

        if not param_set:
            raise CannotGetParameter(param_pair.key)

        for parameter in param_set:
            if not param_pair.is_bool_check():
                result = param_pair.compare(parameter)
            else:
                result = True if parameter else False
            if result:
                break

        return result, element, elems_set

    class ParameterPair:
        def __init__(self, key, value="", sharp=False, operator="=", bool_check=False, arguments=None):
            self.key = key
            self.bool_check = bool_check
            if arguments is None:
                arguments = []
            if not value:
                self.bool_check = True
            self.value = value
            self.prop = 'ParameterPair'
            self.operator = operator
            self.arguments = arguments
            if sharp:
                self.prop = 'Sharp'

        def compare(self, value):
            self.operator = self.operator.replace('*', '')
            if self.operator == "=":
                return self.value == value
            elif self.operator == "!=":
                return self.value != value
            elif self.operator == "<":
                return int(self.value) < int(value)
            elif self.operator == "<=":
                return int(self.value) <= int(value)
            elif self.operator == ">":
                return int(self.value) > int(value)
            elif self.operator == ">=":
                return int(self.value) >= int(value)
            else:
                raise WrongLinkSentence()

        def is_bool_check(self):
            return self.bool_check

    @staticmethod
    def parse_args(arg_string):
        argument_rx = r'([\w:]+)=\(([^\)]*)\)'
        arguments_struct = []
        for arg in re.finditer(argument_rx, arg_string):
            arguments_struct.append({
                'name': arg.group(1),
                'value': arg.group(2)
            })
        return arguments_struct

    def parse_sector(self, sector, element):
        sector = sector.strip()
        for txt_link in list(set(re.findall(r'%[^\)%]+%', sector))):
            sector = sector.replace(
                txt_link, resources.txt_import.Handler.get_link(txt_link.strip('%'))(self.metadata)
            )
        sector_rx = r'([\w:]+)(\*?([<>!=\?]+))\(([^\)]*)\)(\{[^\}]+\})?|\s*([&\|])\s*|(\[\s*(.*?)\s*\])'
        parsed_list = []
        if re.search(r'^#\s*', sector):
            parsed_list.append(self.ParameterPair('#', sharp=True))
            sector = re.sub(r'^#\s*', '', sector)

        parsed_sector = re.finditer(sector_rx, sector)
        for seq in parsed_sector:
            # bracket group
            if re.search(r'^\[.*\]$', seq.group(0)):
                parsed_list.append(self.parse_sector(seq.group(8), element))
            # AND/OR operators
            elif re.search(r'[&\|]', seq.group(0)):
                parsed_list.append(seq.group(6))
            # parameter checking
            elif re.search(r'[<>!=\?]\s*\(', seq.group(0)):
                par_name = seq.group(1)
                operator = seq.group(2)
                value = seq.group(4)
                arguments = self.parse_args(seq.group(5)) if seq.group(5) else []
                if '*' not in operator:
                    parameter_pair = self.ParameterPair(par_name, value, operator=operator, arguments=arguments)
                else:
                    parameter_pair = self.ParameterPair(
                        par_name, element.get_parameter(value), operator=operator, arguments=arguments
                    )
                parsed_list.append(parameter_pair)
            else:
                raise WrongLinkSentence()

        return parsed_list

    def execute_for_element(self, elt, bl):
        if not bl:
            return elt
        for a in self.transmitter.get_applied()['actions']:
            elt = collection.static.Handler.get_func(a.get_path())(elt, a.get_arguments())
        return elt

    def is_good(self, link_slice, element, elems_set, check_function, return_bs=False):
        len_link_slice = len(link_slice)
        complete_list = []

        for i in range(len_link_slice):
            if link_slice[i] in ('&', '|'):
                complete_list.append(link_slice[i])
            elif type(link_slice[i]) == LinkSentence.ParameterPair:
                try:
                    ce_result = self.check_element(element, link_slice[i], elems_set, check_function)
                    complete_list.append(ce_result[0])
                    element = ce_result[1]
                    elems_set = ce_result[2]
                except CannotGetParameter:
                    complete_list.append(False)

            else:
                complete_list.append(self.is_good(link_slice[i], element, elems_set, check_function))

        if '&' in complete_list and '|' in complete_list:
            raise WrongLinkSentence()

        common_operator = '&' if '&' in complete_list else '|' if '|' in complete_list else None

        if not common_operator and (not link_slice or len(link_slice) > 1):
            raise WrongLinkSentence()

        if not common_operator:
            if not return_bs:
                return link_slice[0]
            else:
                return link_slice[0], elems_set, self.execute_for_element(element, link_slice[0])
        elif common_operator == '&':
            blc = False not in complete_list
            if not return_bs:
                return blc, self.execute_for_element(element, blc)
            else:
                return blc, elems_set, self.execute_for_element(element, blc)
        elif common_operator == '|':
            blc = True in complete_list
            if not return_bs:
                return blc, self.execute_for_element(element, blc)
            else:
                return blc, elems_set, self.execute_for_element(element, blc)
        else:
            raise WrongLinkSentence()

    def check(self, element, elems_set, check_function, return_bs=False):
        if element.input_container.config.debug_mode:
            print('LINK:', self.link)
        parsed_list = self.parse_sector(self.link, element)
        return self.is_good(parsed_list, element, elems_set, check_function, return_bs)


class Action:
    def __init__(self, path, arguments=False, branching=False):
        self.path = path
        self.arguments = arguments if arguments else []
        self.branching = branching

    def get_path(self):
        return self.path

    def get_arguments(self):
        return self.arguments

    def get_args(self):
        return self.get_arguments()

    def branching_allowed(self):
        return self.branching


class Temp:
    NULL = '$__NULL__'
    UNALLOCATED = -1.5


class IdIsNotUnique(Exception):
    pass


class ParameterAlreadyExists(Exception):
    pass


class ParameterNotFound(Exception):
    pass


class WrongCollectionPath(Exception):
    pass


class SystemNotFound(Exception):
    pass


class SubsystemNotFound(Exception):
    pass


class WrongFunctionUse(Exception):
    pass


class CannotGetParameter(Exception):
    pass


class WrongLinkSentence(Exception):
    pass


class TypeIsNotStatic(Exception):
    pass


class WrongChildType(Exception):
    pass


class UndefinedSystem(Exception):
    pass


class ClassEntityNotFound(Exception):
    pass


class SystemEntityNotFound(Exception):
    pass


class SubclassesOrderNotSupported(Exception):
    pass


class AddedBehaviourNotSupported(Exception):
    pass


class IntrusionIsEmpty(Exception):
    pass


class IntrusionUnsupportedType(Exception):
    pass


class UnknownForkID(Exception):
    pass


class MalformedSubOrder(Exception):
    pass


class RepeatedClassAssignment(Exception):
    pass


class MainContainerNotFound(Exception):
    pass


class SegMethodNotFound(Exception):
    pass


class CannotCreateBranch(Exception):
    pass
