# The MIT License (MIT)
#
# Copyright (c) 2018 Niklas Rosenstein
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
"""
This module provides some magic functionality that is implemented using
parsing of run-time bytecode.
"""

import dis
import sys

def _build_opstackd():
  """
  Builds a dictionary that maps the name of an op-code to the number of elemnts
  it adds to the stack when executed. For some opcodes, the dictionary may
  contain a function which requires the #dis.Instruction object to determine
  the actual value.

  The dictionary mostly only contains information for instructions
  used in expressions.
  """

  def _call_function_argc(argc):
    func_obj = 1
    args_pos = (argc & 0xff)
    args_kw = ((argc >> 8) & 0xff) * 2
    return func_obj + args_pos + args_kw

  def _make_function_argc(argc):
    args_pos = (argc + 0xff)
    args_kw = ((argc >> 8) & 0xff) * 2
    annotations = (argc >> 0x7fff)
    anootations_names = 1 if annotations else 0
    code_obj = 1
    qualname = 1
    return args_pos + args_kw + annotations + anootations_names + code_obj + qualname

  result = {
    'NOP': 0,
    'POP_TOP': -1,
    'ROT_TWO': 0,
    'ROT_THREE': 0,
    'DUP_TOP': 1,
    'DUP_TOP_TWO': 2,

    # Unary operations
    'GET_ITER': 0,

    # Miscellaneous operations
    'PRINT_EXPR': -1,
    'BREAK_LOOP': 0,  # xxx: verify
    'CONTINUE_LOOP': 0,  # xxx: verify
    'SET_ADD': -1,  # xxx: verify
    'LIST_APPEND': -1,  # xxx: verify
    'MAP_ADD': -2,  # xxx: verify
    'RETURN_VALUE': -1,  # xxx: verify
    'YIELD_VALUE': -1,
    'YIELD_FROM': -1,
    'IMPORT_STAR': -1,

    # 'POP_BLOCK':
    # 'POP_EXCEPT':
    # 'END_FINALLY':
    # 'LOAD_BUILD_CLASS':
    # 'SETUP_WITH':
    # 'WITH_CLEANUP_START':
    # 'WITH_CLEANUP_FINISH':
    'STORE_NAME': -1,
    'DELETE_NAME': 0,
    'UNPACK_SEQUENCE': lambda op: op.arg,
    'UNPACK_EX': lambda op: (op.arg & 0xff) - (op.arg >> 8 & 0xff),  # xxx: check
    'STORE_ATTR': -2,
    'DELETE_ATTR': -1,
    'STORE_GLOBAL': -1,
    'DELETE_GLOBAL': 0,
    'LOAD_CONST': 1,
    'LOAD_NAME': 1,
    'BUILD_TUPLE': lambda op: 1 - op.arg,
    'BUILD_LIST': lambda op: 1 - op.arg,
    'BUILD_SET': lambda op: 1 - op.arg,
    'BUILD_MAP': lambda op: 1 - op.arg,
    'LOAD_ATTR': 0,
    'COMPARE_OP': 1,  # xxx: check
    # 'IMPORT_NAME':
    # 'IMPORT_FROM':
    # 'JUMP_FORWARD':
    # 'POP_JUMP_IF_TRUE':
    # 'POP_JUMP_IF_FALSE':
    # 'JUMP_IF_TRUE_OR_POP':
    # 'JUMP_IF_FALSE_OR_POP':
    # 'JUMP_ABSOLUTE':
    # 'FOR_ITER':
    'LOAD_GLOBAL': 1,
    # 'SETUP_LOOP'
    # 'SETUP_EXCEPT'
    # 'SETUP_FINALLY':
    'LOAD_FAST': 1,
    'STORE_FAST': -1,
    'DELETE_FAST': 0,
    # 'LOAD_CLOSURE':
    'LOAD_DEREF': 1,
    'LOAD_CLASSDEREF': 1,
    'STORE_DEREF': -1,
    'DELETE_DEREF': 0,
    'RAISE_VARARGS': lambda op: -op.arg,
    'CALL_FUNCTION': lambda op: 1 - _call_function_argc(op.arg),
    'MAKE_FUNCTION': lambda op: 1 - _make_function_argc(op.arg),
    # 'MAKE_CLOSURE':
    'BUILD_SLICE': lambda op: 1 - op.arg,
    # 'EXTENDED_ARG':
    'CALL_FUNCTION_KW': lambda op: 1 - _call_function_argc(op.arg),
  }

  if sys.version >= '3.5':
    result.update({
      'BEFORE_ASYNC_WITH': 0,
      'SETUP_ASYNC_WITH': 0,
      # Coroutine operations
      'GET_YIELD_FROM_ITER': 0,
      'GET_AWAITABLE': 0,
      'GET_AITER': 0,
      'GET_ANEXT': 0,
    })

  if sys.version <= '3.5':
    result.update({
      'CALL_FUNCTION_VAR': lambda op: 1 - _call_function_argc(op.arg),
      'CALL_FUNCTION_VAR_KW': lambda op: 1 - _call_function_argc(op.arg),
    })

  for code in dis.opmap.keys():
    if code.startswith('UNARY_'):
      result[code] = 0
    elif code.startswith('BINARY_') or code.startswith('INPLACE_'):
      result[code] = -1

  return result

opstackd = _build_opstackd()

def get_stackdelta(op):
  """
  Returns the number of elements that the instruction *op* adds to the stack.

  # Arguments
  op (dis.Instruction): The instruction to retrieve the stackdelta value for.

  # Raises
  KeyError: If the instruction *op* is not supported.
  """

  res = opstackd[op.opname]
  if callable(res):
    res = res(op)
  return res

def get_assigned_name(frame):
  """
  Checks the bytecode of *frame* to find the name of the variable a result is
  being assigned to and returns that name. Returns the full left operand of the
  assignment. Raises a #ValueError if the variable name could not be retrieved
  from the bytecode (eg. if an unpack sequence is on the left side of the
  assignment).

  > **Known Limitations**:  The expression in the *frame* from which this
  > function is called must be the first part of that expression. For
  > example, `foo = [get_assigned_name(get_frame())] + [42]` works,
  > but `foo = [42, get_assigned_name(get_frame())]` does not!

  ```python
  >>> var = get_assigned_name(sys._getframe())
  >>> assert var == 'var'
  ```

  __Available in Python 3.4, 3.5__
  """

  SEARCHING, MATCHED = 1, 2
  state = SEARCHING
  result = ''
  stacksize = 0

  for op in dis.get_instructions(frame.f_code):
    if state == SEARCHING and op.offset == frame.f_lasti:
      if not op.opname.startswith('CALL_FUNCTION'):
        raise RuntimeError('get_assigned_name() requires entry at CALL_FUNCTION')
      state = MATCHED

      # For a top-level expression, the stack-size should be 1 after
      # the function at which we entered was executed.
      stacksize = 1
    elif state == MATCHED:
      # Update the would-be size of the stack after this instruction.
      # If we're at zero, we found the last instruction of the expression.
      try:
        stacksize += get_stackdelta(op)
      except KeyError:
        raise RuntimeError('could not determined assigned name, instruction '
            '{} is not supported'.format(op.opname))
      if stacksize == 0:
        if op.opname not in ('STORE_NAME', 'STORE_ATTR', 'STORE_GLOBAL', 'STORE_FAST'):
          raise ValueError('expression is not assigned or branch is not first part of the expression')
        return result + op.argval
      elif stacksize < 0:
        raise ValueError('not a top-level expression')

      if op.opname.startswith('CALL_FUNCTION'):
        # Chained or nested function call.
        raise ValueError('inside a chained or nested function call')
      elif op.opname == 'LOAD_ATTR':
        result += op.argval + '.'

  if not result:
    raise RuntimeError('last frame instruction not found')
  assert False
