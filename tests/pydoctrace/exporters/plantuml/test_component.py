from io import StringIO
from typing import Any, Dict, Iterable, Union

from pytest import fixture, mark

from pydoctrace.domain.diagram import Call, Function, Module, Raised, Return
from pydoctrace.domain.execution import CallEnd, Error
from pydoctrace.exporters.plantuml.component import (
    PLANTUML_COMPONENT_FORMATTER, ModuleStructureVisitor, PlantUMLComponentExporter
)


@fixture(scope='function')
def exporter_without_writer() -> PlantUMLComponentExporter:
    return PlantUMLComponentExporter(None)


@mark.parametrize(
    ['text_to_format', 'values_by_key', 'formatted_text'],
    [
        ('', {}, ''),
        ('@startuml {diagram_name}', {
            'diagram_name': 'diagram_name'
        }, '@startuml diagram_name'),

        # no need to replace '@' occurrences in the PlantUML component diagram syntax
        ('function {decorator}', {
            'decorator': '@tracer'
        }, 'function @tracer'),

        # '__' occurrences are escaped only when specified by the 'dunder' format_spec
        ('{styling} {name:dunder}', {
            'styling': '__italic__',
            'name': '__main__'
        }, '__italic__ ~__main~__'),
    ]
)
def test_plantuml_component_formatter(text_to_format: str, values_by_key: Dict[str, Any], formatted_text):
    assert PLANTUML_COMPONENT_FORMATTER.format(text_to_format, **values_by_key) == formatted_text


def test_plantuml_component_exporter_function_from_call(exporter_without_writer: PlantUMLComponentExporter):
    call_end = CallEnd(
        'pydoctrace.exporters.plantuml.component', ('pydoctrace', 'exporters', 'plantuml', 'component'),
        'function_from_call', 162
    )

    # the exporter starts with an empty cache of functions
    assert len(exporter_without_writer.functions) == 0, 'functions cache must be empty'

    # creates the function and ensures that it is in the cache
    function = exporter_without_writer.function_from_call(call_end)
    assert function.name == 'function_from_call'
    assert function.module_path == ('pydoctrace', 'exporters', 'plantuml', 'component')
    assert function.fqn == 'pydoctrace.exporters.plantuml.component.function_from_call'

    assert len(exporter_without_writer.functions) == 1, 'the cache must carry the function'
    assert exporter_without_writer.functions[('pydoctrace', 'exporters', 'plantuml', 'component', 'function_from_call')
                                            ] == function

    # on the 2nd call, the function is retrieved from the cache
    function_2 = exporter_without_writer.function_from_call(call_end)
    assert function_2 is function
    assert len(exporter_without_writer.functions) == 1, 'the cache must carry the function'
    assert exporter_without_writer.functions[('pydoctrace', 'exporters', 'plantuml', 'component', 'function_from_call')
                                            ] == function_2


def test_plantuml_component_exporter_next_interaction_rank(exporter_without_writer: PlantUMLComponentExporter):
    exporter = PlantUMLComponentExporter(None)
    assert exporter.next_interaction_rank() == 1, 'first interaction rank must be 1'
    assert exporter.next_interaction_rank() == 2, 'next interaction rank must be 2'
    assert exporter.next_interaction_rank() == 3, 'next interaction rank must be 3'

    # the ranks of another exporter should start at 1
    other_exporter = PlantUMLComponentExporter(None)
    assert other_exporter.next_interaction_rank() == 1, 'first interaction rank must be 1'
    assert other_exporter.next_interaction_rank() == 2, 'next interaction rank must be 2'
    assert other_exporter.next_interaction_rank() == 3, 'next interaction rank must be 3'


@mark.parametrize(
    ['ranks', 'label_ranks'], [
        ([], ''),
        ([1], '1'),
        ([1, 2], '1, 2'),
        ([1, 2, 3, 4, 5, 6, 7], '1, 2, 3, 4, 5, 6, 7'),
        ([1, 2, 3, 4, 5, 6, 7, 8], '1, 2, 3 ... 6, 7, 8'),
    ]
)
def test_plantuml_component_exporter_build_arrow_label_ranks(
    exporter_without_writer: PlantUMLComponentExporter, ranks: Iterable[Union[int, str]], label_ranks: str
):
    assert exporter_without_writer.build_arrow_label_ranks(ranks) == label_ranks


@mark.parametrize(
    ['functions', 'expected_root_module'], [
        (
            [Function('main', ('__main__', ))
            ], Module(None, {'__main__': Module('__main__', {}, {'main': Function('main', ('__main__', ))})}, {})
        ),
        (
            [Function('main',
                      ('__main__', )), Function('trace', ('pydoctrace', 'tracer'))],
            Module(
                None, {
                    '__main__':
                    Module('__main__', {}, {'main': Function('main', ('__main__', ))}),
                    'pydoctrace':
                    Module(
                        'pydoctrace',
                        {'tracer': Module('tracer', {}, {'trace': Function('trace', ('pydoctrace', 'tracer'))})}, {}
                    ),
                }, {}
            )
        ),
    ]
)
def test_plantuml_component_exporter_build_components_structure(
    exporter_without_writer: PlantUMLComponentExporter, functions: Iterable[Function], expected_root_module: Module
):
    assert exporter_without_writer.build_components_structure(functions) == expected_root_module


@mark.parametrize(
    ['traced_function', 'visited_module', 'parent_module_path', 'indentation_level', 'expected_plantuml_lines'],
    [
        # the traced function is the only function in the __main__ module
        (
            Function('main', ('__main__', )),
            Module(None, {'__main__': Module('__main__', {}, {'main': Function('main', ('__main__', ))})}, {}), (), 0, [
                'rectangle ~__main~__ #line:transparent;text:transparent {\n',
                '  [~__main~__.main] as "main" << @trace_to_component_puml >>\n',
                '}\n',
            ]
        ),
        # distinguish the traced function from the other function
        (
            Function('main', ('__main__', )),
            Module(
                None, {
                    '__main__':
                    Module(
                        '__main__', {}, {
                            'main': Function('main', ('__main__', )),
                            'trace': Function('trace', ('__main__', )),
                        }
                    )
                }, {}
            ), (), 0, [
                'rectangle ~__main~__ #line:transparent;text:transparent {\n',
                '  [~__main~__.main] as "main" << @trace_to_component_puml >>\n',
                '  [~__main~__.trace] as "trace"\n',
                '}\n',
            ]
        ),
        # case with 2 sibling modules (it produces a transparent wrapping rectangle around the 2 code modules)
        (
            Function('main', ('__main__', )),
            Module(
                None, {
                    '__main__': Module('__main__', {}, {
                        'main': Function('main', ('__main__', )),
                    }),
                    'pydoctrace': Module('pydoctrace', {}, {
                        'trace': Function('trace', ('__main__', )),
                    }),
                }, {}
            ), (), 0, [
                'rectangle None #line:transparent;text:transparent {\n',
                '  frame ~__main~__ {\n',
                '    [~__main~__.main] as "main" << @trace_to_component_puml >>\n',
                '  }\n',
                '  frame pydoctrace {\n',
                '    [~__main~__.trace] as "trace"\n',
                '  }\n',
                '}\n',
            ]
        ),
        # modules without function are considered as packages
        (
            Function('trace', ('pydoctrace', 'tracer')),
            Module(
                None, {
                    'pydoctrace':
                    Module(
                        'pydoctrace',
                        {'tracer': Module('tracer', {}, {'trace': Function('trace', ('pydoctrace', 'tracer'))})}, {}
                    )
                }, {}
            ), (), 0, [
                'package pydoctrace {\n', '  frame tracer {\n',
                '    [pydoctrace.tracer.trace] as "trace" << @trace_to_component_puml >>\n', '  }\n', '}\n'
            ]
        ),
        # parent modules without functions are concatenated
        (
            Function('trace', ('pydoctrace', 'tracer')),
            Module(
                None, {
                    'pydoctrace':
                    Module(
                        'pydoctrace', {
                            'tracing':
                            Module(
                                'tracing', {
                                    'tracer':
                                    Module(
                                        'tracer', {}, {'trace': Function('trace', ('pydoctrace', 'tracing', 'tracer'))}
                                    )
                                }, {}
                            )
                        }, {}
                    )
                }, {}
            ), (), 0, [
                'package pydoctrace.tracing {\n',
                '  frame tracer {\n',
                '    [pydoctrace.tracing.tracer.trace] as "trace"\n',
                '  }\n',
                '}\n',
            ]
        ),
    ]
)
def test_module_structure_visitor_visit_module(
    traced_function, visited_module, parent_module_path, indentation_level, expected_plantuml_lines
):
    module_visitor = ModuleStructureVisitor(traced_function)

    for line_index, (plantuml_line, expected_line) in enumerate(zip(module_visitor.visit_module(
            visited_module, parent_module_path, indentation_level), expected_plantuml_lines)):
        assert plantuml_line == expected_line, f"at index {line_index}, '{plantuml_line}' is expected to be '{expected_line}'"


@mark.parametrize(
    ['traced_function', 'visited_functions', 'indentation_level', 'expected_plantuml_lines'], [
        (
            Function('do_thing', ('tests', 'tracer')), [
                Function('do_thing', ('tests', 'tracer')),
            ], 0, [
                '[tests.tracer.do_thing] as "do_thing" << @trace_to_component_puml >>\n',
            ]
        ),
        (
            Function('do_thing', ('tests', 'tracer')), [
                Function('do_thing', ('tests', 'tracer')),
            ], 1, [
                '  [tests.tracer.do_thing] as "do_thing" << @trace_to_component_puml >>\n',
            ]
        ),
        (
            Function('do_thing', ('tests', 'tracer')), [
                Function('do_something_else', ('tests', 'tracer')),
            ], 0, [
                '[tests.tracer.do_something_else] as "do_something_else"\n',
            ]
        ),
        (
            Function('do_thing', ('tests', 'tracer')), [
                Function('do_thing', ('tests', 'tracer')),
                Function('do_something_else', ('tests', 'tracer')),
            ], 0, [
                '[tests.tracer.do_thing] as "do_thing" << @trace_to_component_puml >>\n',
                '[tests.tracer.do_something_else] as "do_something_else"\n',
            ]
        ),
    ]
)
def test_module_structure_visitor_visit_functions(
    traced_function, visited_functions, indentation_level, expected_plantuml_lines
):
    module_visitor = ModuleStructureVisitor(traced_function)

    for line_index, (plantuml_line, expected_line) in enumerate(zip(module_visitor.visit_functions(
            visited_functions, indentation_level), expected_plantuml_lines)):
        assert plantuml_line == expected_line, f"at index {line_index}, '{plantuml_line}' is expected to be '{expected_line}'"


def test_plantuml_component_exporter_on_headers():
    exported_contents = StringIO()
    exporter = PlantUMLComponentExporter(exported_contents)
    exporter.on_header('math_cli.__main__', 'factorial')
    assert exported_contents.getvalue().startswith('@startuml math_cli.__main__.factorial-component\n')


def test_plantuml_component_exporter_on_tracing_start(exporter_without_writer: PlantUMLComponentExporter):
    start_called = CallEnd('math_cli.__main__', ('math_cli', '__main__'), 'factorial', 16)

    # the exporter is initialized without reference to the traced function
    assert exporter_without_writer.traced_function is None

    # then the exporter knows which function started the tracing
    exporter_without_writer.on_tracing_start(start_called)
    assert exporter_without_writer.traced_function == Function('factorial', ('math_cli', '__main__'))


def test_plantuml_component_exporter_on_start_call(exporter_without_writer: PlantUMLComponentExporter):
    caller = CallEnd('math_cli.controller', ('math_cli', 'controller'), 'factorial', 25)
    called = CallEnd('math_cli.validator', ('math_cli', 'validator'), 'is_positive_int', 4)

    # the exporter is initialized with an empty cache of calls between functions
    assert exporter_without_writer.interactions_by_call is not None
    assert len(exporter_without_writer.interactions_by_call) == 0

    # notifies the exporter that a call starts
    exporter_without_writer.on_start_call(caller, called)

    assert len(exporter_without_writer.interactions_by_call) == 1
    call_interaction = exporter_without_writer.interactions_by_call[
        Function('factorial', ('math_cli', 'controller')),
        Function('is_positive_int', ('math_cli', 'validator'))]
    assert len(call_interaction.calls) == 1
    assert len(call_interaction.responses) == 0
    assert Call(1) in call_interaction.calls


def test_plantuml_component_exporter_on_error_propagation(exporter_without_writer: PlantUMLComponentExporter):
    caller = CallEnd('math_cli.__main__', ('math_cli', '__main__'), 'factorial', 4)
    called = CallEnd('math_cli.validator', ('math_cli', 'validator'), 'validate_positive_int', 25)
    validation_error = Error('ValueError', 'must be a positive integer')
    assert len(exporter_without_writer.interactions_by_call) == 0

    # notifies the exporter that an error is raised by the called to the caller
    exporter_without_writer.on_error_propagation(called, caller, validation_error)

    assert len(exporter_without_writer.interactions_by_call) == 1
    call_interaction = exporter_without_writer.interactions_by_call[
        Function('factorial', ('math_cli', '__main__')),
        Function('validate_positive_int', ('math_cli', 'validator'))]
    assert len(call_interaction.calls) == 0
    assert len(call_interaction.responses) == 1
    assert Raised(1, 'ValueError') in call_interaction.responses


def test_plantuml_component_exporter_on_return(exporter_without_writer: PlantUMLComponentExporter):
    caller = CallEnd('math_cli.controller', ('math_cli', 'controller'), '__main__', 25)
    called = CallEnd('math_cli.compute', ('math_cli', 'compute'), 'factorial', 4)
    returned_value = 24
    assert len(exporter_without_writer.interactions_by_call) == 0

    # notifies the exporter that a value is returned by the called to the caller
    exporter_without_writer.on_return(caller=caller, called=called, arg=returned_value)

    assert len(exporter_without_writer.interactions_by_call) == 1
    call_interaction = exporter_without_writer.interactions_by_call[Function('__main__', ('math_cli', 'controller')),
                                                                    Function('factorial', ('math_cli', 'compute'))]
    assert len(call_interaction.calls) == 0
    assert len(call_interaction.responses) == 1
    assert Return(1) in call_interaction.responses
