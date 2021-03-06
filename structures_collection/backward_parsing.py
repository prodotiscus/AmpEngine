#!/usr/bin/python3

from collections import namedtuple
import datrie
import itertools
import grammar
import structures_collection.char_level
import structures_collection.minor as mnr
import structures_collection.static


class HandlerStart:
    def __init__(self):
        self.parsers = {}

    def get_parser(self, parent_system, child_system):
        if (parent_system, child_system) in self.parsers:
            return self.parsers[(parent_system, child_system)]
        else:
            raise ParserNotFound(parent_system, child_system)

    def add_parser(self, parent_system, child_system, func):
        self.parsers[(parent_system, child_system)] = func

    def to_values(self, parent_system):
        return [x[1] for x in self.parsers if x[0] == parent_system]


Handler = HandlerStart()


def new_parser(parent_system, child_system):
    def parser_decorator(func):
        Handler.add_parser(parent_system, child_system, func)

        def wrapped(function_arg1):
            return func(function_arg1)

        return wrapped
    return parser_decorator


bp_cache = {
    "universal:morpheme_by_init_char": {},
    "grammar_nulls": [],
    "container_trie": None
}


class IterativeSingleSegmentation:
    def __init__(self, container, input_container_element, frame_string, co_start):
        self.container = container
        if bp_cache["container_trie"] is None:
            morpheme_chars = ""
            morphemes = self.container.iter_content_filter(
                lambda x: not x.startswith('_^'),
                sort_desc=True,
                system_filter='universal:morpheme'
            )
            for morpheme in morphemes:
                if morpheme.get_content() != grammar.Temp.NULL:
                    morpheme_chars += morpheme.get_clear_content()
            morpheme_chars = ''.join(ch for ch in set(morpheme_chars))
            bp_cache["container_trie"] = datrie.Trie(morpheme_chars)
            for morpheme in morphemes:
                body = mnr.Clear.remove_spec_chars('universal:morpheme', morpheme.get_content())
                if body not in bp_cache["container_trie"]:
                    bp_cache["container_trie"][body] = [morpheme.get_id()]
                else:
                    bp_cache["container_trie"][body].append(morpheme.get_id())

        self.input_container_element = input_container_element
        self.frame_string = frame_string
        self.co_start = co_start
        self.elements_on_id = dict()

    def generate_char_outlines(self, left_id_sequence):
        co_list = []
        for element_id in left_id_sequence:
            co_local = structures_collection.char_level.CharOutline(
                [],
                attachment=self.elements_on_id[element_id].get_clear_content(),
                metadata={'mc_id': element_id}
            )
            if self.elements_on_id[element_id].get_content() != grammar.Temp.NULL:
                co_local.add_group(
                    structures_collection.char_level.CharIndexGroup(
                        [self.co_start, self.co_start + len(self.elements_on_id[element_id].get_content()) - 1]
                    )
                )
                self.co_start += len(self.elements_on_id[element_id].get_content())
            else:
                co_local.add_group(
                    structures_collection.char_level.CharIndexGroup(
                        [-1, -1], is_virtual=True
                    )
                )
            co_list.append(co_local)
        return co_list

    def start(self):
        branches = self.extract_sequences([], self.frame_string)
        if not branches:
            return None
        for branch_cat in branches:
            for j, sequence in enumerate(itertools.product(*branch_cat)):
                if j > 200:
                    break
                for element_id in sequence:
                    self.elements_on_id[element_id] = self.container.get_by_id(element_id)
                csc = self.common_sequence_check(list(sequence))
                if csc:
                    return csc
                else:
                    pass
        return None

    def extract_sequences(self, left_id_sequence, substring):
        branches = []
        prefix_items = bp_cache["container_trie"].prefix_items(substring)
        if not prefix_items:
            return False
        for (prefix, element_ids) in prefix_items:
            new_sequence = left_id_sequence + [element_ids]
            branch = self.extract_sequences(new_sequence, substring[len(prefix):])
            if branch:
                branches.extend(branch)
            elif substring[len(prefix):] == "":
                branches.append(new_sequence)

        return branches

    def common_sequence_check(self, id_sequence):
        if not self.check_sequence(id_sequence):
            return False
        avnulls = self.check_avnulls_of_sequence(id_sequence)
        #if not self.check_prw_of_sequence(id_sequence):
        #    return False
        orders = self.container.get_system('universal:morpheme').get_subcl_orders_affecting_ids(id_sequence)
        for order in orders:
            order_check = self.check_sequence_by_order(id_sequence, order, avnulls)
            if not order_check.order_works:
                if order_check.strict:
                    return False
            else:
                id_sequence = [elem.get_id() for elem in order_check.sequence]
        return id_sequence

    def check_sequence(self, id_sequence):
        el_seq = [self.elements_on_id[x] for x in id_sequence]
        bses = el_seq
        for j, elem in enumerate(el_seq):
            elem.set_transmitter_local_index(j)
        for j, elem in enumerate(el_seq):
            for link in elem.get_applied()['links']:
                lc_bool, bses, self.input_container_element = link.check(
                    self.input_container_element, bses, lambda x: True, return_bs=True
                )
                if not lc_bool:
                    return False
        return True

    def check_avnulls_of_sequence(self, id_sequence):
        el_seq = [self.elements_on_id[x] for x in id_sequence]
        for e, elem in enumerate(el_seq):
            elem.set_transmitter_local_index(e)
        available_nulls = []
        if not bp_cache["grammar_nulls"]:
            bp_cache["grammar_nulls"] = self.container.iter_content_filter(
                lambda x: x == grammar.Temp.NULL, system_filter='universal:morpheme'
            )
        grammar_nulls = bp_cache["grammar_nulls"]
        bsid_obj = el_seq + grammar_nulls
        for e, null in enumerate(grammar_nulls):
            null.set_transmitter_local_index(len(el_seq) + e)
        for e, null in enumerate(grammar_nulls):
            for link in null.get_applied()['links']:
                # BS Array
                lc_bool, bsid_obj, input_container_element = link.check(
                    self.input_container_element, bsid_obj, lambda x: True, return_bs=True
                )
                if lc_bool:
                    self.elements_on_id[null.get_id()] = null
                    available_nulls.append(null)
        return available_nulls

    def check_sequence_by_order(self, id_sequence, order, available_nulls):
        result = namedtuple("result", ["order_works", "strict", "sequence"])
        el_seq = [self.elements_on_id[x] for x in id_sequence]
        order_check = order.check_sequence(el_seq, available_nulls)
        return result(order_check["check"], order.is_strict(), order_check["cn_sequence"])

    def check_prw_of_sequence(self, id_sequence):
        act_list = [self.elements_on_id[x].get_applied()['actions'] for x in id_sequence]
        params_list = [
            structures_collection.static.Handler.get_func_params(x.get_path()) for x in itertools.chain(*act_list)
        ]
        params_list = list(itertools.chain(*params_list))
        return len(params_list) == len(set(params_list))


def decode_asterisk_pattern(pattern):
    pattern = pattern.replace('\\', '')
    return 'class' if pattern[1] == '.' else 'id', pattern[2:-1]


def get_null_id(decoded_value, container):
    if decoded_value[0] == 'id':
        return decoded_value[1]
    elif decoded_value[0] == 'class':
        class_elements = container.get_class(decoded_value[1])
        for element in class_elements:
            if element == grammar.Temp.NULL:
                return element.get_id()
        return None
    else:
        raise ValueError()


@new_parser(parent_system='universal:token', child_system='universal:morpheme')
def morpheme_in_token(input_container_element, container, input_container):
    if input_container.ic_log.get_sector("STEMS_EXTRACTED") is None:
        raise InternalParserException('No stem extractor provided')
    stems = input_container.ic_log.get_log_sequence("STEMS_EXTRACTED", element_id=input_container_element.get_ic_id())
    if not stems:
        raise InternalParserException(
            'No stems found for <{}> (={})'.format(
                input_container_element.get_ic_id(), input_container_element.get_content()
            )
        )

    group_index = 0
    for n, stem in enumerate(stems):
        if len(stem.get_prop('positions')) >= len(input_container_element.get_content()):
            continue
        co_start = stem.get_prop('positions')[-1] + 1
        iss_instance = IterativeSingleSegmentation(
            container,
            input_container_element,
            input_container_element.get_content()[co_start:],
            co_start
        )
        try:
            markup = iss_instance.start()
        except RecursionError:
            markup = None
        if markup is not None:
            markup_outlines = iss_instance.generate_char_outlines(markup)
            input_container.segment_element(
                input_container_element, 'universal:morpheme', markup_outlines, set_group=group_index
            )
            group_index += 1


class ParserNotFound(Exception):
    pass


class InternalParserException(Exception):
    pass


class SegmentationIterFailed(Exception):
    pass
