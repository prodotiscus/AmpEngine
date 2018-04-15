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


@new_link('MANSI_CONS2')
def mansi_cons_two(input_container):
    """
    MANSI_CONS2
    :param input_container: IC container
    :return: compared value [Str]
    """

    return "[^ёуезыаоэяию]{2}"


class LinkNotFound(Exception):
    pass