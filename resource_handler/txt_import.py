#!/usr/bin/python3


class HandlerStart:
    def __init__(self):
        self.links = {}
        self.params_provided = {}

    def get_link(self, link_name):
        if link_name in self.links:
            return self.links[link_name]
        else:
            raise LinkNotFound()

    def add_link(self, link_name, value):
        self.links[link_name] = value


# every function should return List


Handler = HandlerStart()


def new_link(link_name):

    def link_decorator(link):
        Handler.add_link(link_name, link)

        def wrapped(function_arg1):
            return link(function_arg1)

        return wrapped

    return link_decorator


@new_link('MANSI_CONS2_END')
def mansi_cons_two(metadata):
    """
    MANSI_CONS2
    :param metadata: IC container
    :return: compared value [Str]
    """

    return "[^ёуеыаоэяию]{2}$"


@new_link('MANSI_CONS+I')
def mansi_cons_and_i(metadata):
    return "[^ёуезаоэяию]"


@new_link('MANSI_CONS_END')
def mansi_cons_end(metadata):
    return "[^ёуеыаоэяию]$"


@new_link('MANSI_CONS_TWO_MORE_END')
def mansi_cons_two_more_end(metadata):
    return "[^ёуеыаоэяию]{2,}$"


@new_link('MANSI_VOW_END')
def mansi_cons_end(metadata):
    return "[ёуеыаоэяию]$"


@new_link('MANSI_VOW')
def mansi_cons_end(metadata):
    return "[ёуеыаоэяию]"


@new_link('MANSI_CONS')
def mansi_cons(metadata):
    return "[^ёуеыаоэяию]"


@new_link('MANSI_CONS_1,2_END')
def mansi_cons_one_two(metadata):
    return "[^ёуеыаоэяию]{1,2}$"


class LinkNotFound(Exception):
    pass
