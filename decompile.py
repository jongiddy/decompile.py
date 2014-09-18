#
# decompile.py - decompile Python code objects
#
# Copyright (c) 2001 Jonathan Patrick Giddy
#
# Permission is hereby granted, free of charge, to any person obtaining 
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
# 
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

# Send comments to:
# Jonathan Giddy, jongiddy@pobox.co.uk

# version 0.9
# Date 21 January 2005
# - no code changes, added MIT licence, updated email address
# - there will be no v1.0 - try decompyle instead

# version 0.8
# Date 25 January 2001

__version__ = '0.9'

import dis, string, sys, types

VARARGS = 4
KWARGS = 8

PRECEDENCE_ATOM = 24
PRECEDENCE_POWER = 17
PRECEDENCE_UNARY = 16
PRECEDENCE_MULT = 15
PRECEDENCE_ADD = 14
PRECEDENCE_SHIFT = 13
PRECEDENCE_BAND = 12
PRECEDENCE_BXOR = 11
PRECEDENCE_BOR = 10
PRECEDENCE_CMP = 9
PRECEDENCE_IS = 8
PRECEDENCE_IN = 7
PRECEDENCE_NOT = 6
PRECEDENCE_AND = 5
PRECEDENCE_OR = 4
PRECEDENCE_LAMBDA = 3
PRECEDENCE_ARG = PRECEDENCE_LAMBDA
PRECEDENCE_COMMA = 1
PRECEDENCE_NONE = 0

def current_line(code, i):
    tab = code.co_lnotab
    line = code.co_firstlineno
    stopat = i
    addr = 0
    for i in range(0, len(tab), 2):
        addr = addr + ord(tab[i])
        if addr > stopat:
            break
        line = line + ord(tab[i+1])
    return line

class Expression:

    def __init__(self, value, precedence):
        self.value = value
        self.precedence = precedence

    def __repr__(self):
        return 'Expression(%s, %s)' % (`self.value`, `self.precedence`)
    
    def __str__(self):
        return str(self.value)

    def Precedence(self):
        return self.precedence
    
    def Value(self):
        return self.value

    def GetString(self, precedence):
        if self.Precedence() < precedence:
            return '(%s)' % self
        else:
            return str(self)

class Atom(Expression):

    def __init__(self, value):
        Expression.__init__(self, value, PRECEDENCE_ATOM)

class Constant(Atom):

    def __str__(self):
        if self.value is Ellipsis:
            return '...'
        else:
            return repr(self.value)
        
class Local(Atom):
    pass

class Global(Atom):
    pass

class Map(Atom):

    def __init__(self):
        Atom.__init__(self, [])

    def __str__(self):
        return '{%s}' % string.join(self.value, ', ')

    def SetAttr(self, name, value):
        self.value.append("%s: %s" % (name, value))

class Tuple(Atom):

    def __init__(self, values):
        Atom.__init__(self, values)

    def __str__(self):
        values = self.Value()
        if len(values) == 0:
            return '()'
        elif len(values) == 1:
            # This doesn't need the parens immediately, but
            # it emphasises the prescence of the comma, and
            # confirms that it is a 1-tuple
            return '(%s,)' % values[0]
        else:
            return string.join(values, ', ')

    def Precedence(self):
        if len(self.value) <= 1:
            return PRECEDENCE_ATOM
        else:
            return PRECEDENCE_COMMA

    def Value(self):
        return tuple(self.value)
            
class CodeCursor:

    def __init__(self, code):
        self.code = code  # code object
        self.i = 0        # instruction pointer
        self.extend = 0   # extended opcodes
        self.lineno = 1   # minimum possible line number
        self.lastop = 0   # pointer to last operator read
        self.stopi = [len(code.co_code)]

    def GetPosition(self):
        return self.i

    def AtEnd(self):
        return self.i == self.stopi[0]
    
    def GetLine(self):
        return max(self.lineno, current_line(self.code, self.lastop))

    def SetLine(self, lineno):
        assert lineno >= self.lineno, `lineno, self.lineno`
        self.lineno = lineno
        
    def PushStop(self, i):
        self.stopi.append(i)

    def PopStop(self):
        return self.stopi.pop()

    def NextOpcode(self):
        if self.i < self.stopi[-1]:
            c = self.code.co_code[self.i]
            op = ord(c)
            opcode = dis.opname[op]
            if opcode == 'EXTENDED_ARG':
                self.i = self.i + 1
                self.extend = self.ReadOperand()
                return self.NextOpcode()
        else:
            opcode = None
        return opcode

    def ReadOpcode(self, *args):
        opcode = self.NextOpcode()
        assert opcode is not None
        if args:
            assert opcode in args, `self.i, opcode`
        self.lastop = self.i
        self.i = self.i + 1
        return opcode

    def ReadOperand(self):
        assert self.i + 1 < self.stopi[-1], `self.i, self.stopi`
        co_code = self.code.co_code
        operand = ord(co_code[self.i]) + ord(co_code[self.i+1])*256 + \
                  (self.extend << 16)
        self.extend = 0
        self.i = self.i + 2
        return operand

    def GetConstant(self, n):
        return self.code.co_consts[n]

    def GetLocal(self, n):
        assert n < len(self.code.co_varnames), `n, self.code.co_varnames`
        return self.code.co_varnames[n]
    
    def GetName(self, n):
        assert n < len(self.code.co_names), `n, self.code.co_names`
        return self.code.co_names[n]
    
class Decompiler:

    def __init__(self, version):
        self.version = version
        self.stack = []
        self.lines = {}
        self.global_decl = {}
        self.loop = None
    
    def decompile(self, code, *termop):
        try:
            self.code = code
            opcode = code.NextOpcode()
            while opcode is not None and opcode not in termop:
                opcode = string.replace(opcode, '+', '_')
                method = getattr(self, opcode)
                apply(method, (code,))
                opcode = code.NextOpcode()
        except:
            dis.dis(code.code)
            print
            raise

    def getstack(self):
        return self.stack
    
    def getsource(self, indent):
        assert not self.stack, `self.stack`
        lines = {}
        if not self.lines:
            self.lines[self.code.GetLine()] = 'pass'
        for key, value in self.lines.items():
            lines[key] = '    ' * indent + value
        return lines

    def addline(self, lineno, line):
        assert type(line) == type(''), `line`
        prev = self.lines.get(lineno)
        if prev is None:
            self.lines[lineno] = line
        else:
            self.lines[lineno] = '%s; %s' % (prev, line)

    def addclause(self, lineno, head, body):
        if body.has_key(lineno):
            if 0:
                assert len(body) == 1, `body`
                self.addline(lineno, "%s %s" % (head, string.strip(body[lineno])))
            else:
                line = body[lineno]
                self.addline(lineno, "%s %s" % (head, string.strip(line)))
                del body[lineno]
                self.lines.update(body)
                body[lineno] = line
        else:
            self.addline(lineno, head)
            self.lines.update(body)
        self.code.SetLine(max(body.keys()) + 1)

    def SET_LINENO(self, code):
        code.ReadOpcode('SET_LINENO')
        code.ReadOperand()

    def BINARY_ADD(self, code):
        code.ReadOpcode('BINARY_ADD')
        y = self.stack.pop().GetString(PRECEDENCE_ADD+1)
        x = self.stack.pop().GetString(PRECEDENCE_ADD)
        self.stack.append(Expression('%s + %s' % (x, y), PRECEDENCE_ADD))

    def BINARY_AND(self, code):
        code.ReadOpcode('BINARY_AND')
        y = self.stack.pop().GetString(PRECEDENCE_BAND+1)
        x = self.stack.pop().GetString(PRECEDENCE_BAND)
        self.stack.append(Expression('%s & %s' % (x, y), PRECEDENCE_BAND))

    def BINARY_DIVIDE(self, code):
        code.ReadOpcode('BINARY_DIVIDE')
        y = self.stack.pop().GetString(PRECEDENCE_MULT+1)
        x = self.stack.pop().GetString(PRECEDENCE_MULT)
        self.stack.append(Expression('%s / %s' % (x, y), PRECEDENCE_MULT))

    def BINARY_LSHIFT(self, code):
        code.ReadOpcode('BINARY_LSHIFT')
        y = self.stack.pop().GetString(PRECEDENCE_SHIFT+1)
        x = self.stack.pop().GetString(PRECEDENCE_SHIFT)
        self.stack.append(Expression('%s << %s' % (x, y), PRECEDENCE_SHIFT))

    def BINARY_MODULO(self, code):
        code.ReadOpcode('BINARY_MODULO')
        y = self.stack.pop().GetString(PRECEDENCE_MULT+1)
        x = self.stack.pop().GetString(PRECEDENCE_MULT)
        self.stack.append(Expression('%s %% %s' % (x, y), PRECEDENCE_MULT))

    def BINARY_MULTIPLY(self, code):
        code.ReadOpcode('BINARY_MULTIPLY')
        y = self.stack.pop().GetString(PRECEDENCE_MULT+1)
        x = self.stack.pop().GetString(PRECEDENCE_MULT)
        self.stack.append(Expression('%s * %s' % (x, y), PRECEDENCE_MULT))

    def BINARY_OR(self, code):
        code.ReadOpcode('BINARY_OR')
        y = self.stack.pop().GetString(PRECEDENCE_BOR+1)
        x = self.stack.pop().GetString(PRECEDENCE_BOR)
        self.stack.append(Expression('%s | %s' % (x, y), PRECEDENCE_BOR))

    def BINARY_POWER(self, code):
        code.ReadOpcode('BINARY_POWER')
        y = self.stack.pop()
        if y.Precedence() == PRECEDENCE_POWER:
            # include ** in parentheses because the correct order is poorly
            # understood, and is the opposite of the other binary operators
            y = y.GetString(PRECEDENCE_ATOM)
        else:
            y = y.GetString(PRECEDENCE_UNARY)
        x = self.stack.pop().GetString(PRECEDENCE_ATOM)
        self.stack.append(Expression('%s ** %s' % (x, y), PRECEDENCE_POWER))

    def BINARY_RSHIFT(self, code):
        code.ReadOpcode()
        y = self.stack.pop().GetString(PRECEDENCE_SHIFT+1)
        x = self.stack.pop().GetString(PRECEDENCE_SHIFT)
        self.stack.append(Expression('%s >> %s' % (x, y), PRECEDENCE_SHIFT))

    def BINARY_SUBSCR(self, code):
        code.ReadOpcode()
        y = self.stack.pop().GetString(PRECEDENCE_NONE)
        x = self.stack.pop().GetString(PRECEDENCE_ATOM)
        self.stack.append(Expression('%s[%s]' % (x, y), PRECEDENCE_ATOM))

    def BINARY_SUBTRACT(self, code):
        code.ReadOpcode()
        y = self.stack.pop().GetString(PRECEDENCE_ADD+1)
        x = self.stack.pop().GetString(PRECEDENCE_ADD)
        self.stack.append(Expression('%s - %s' % (x, y), PRECEDENCE_ADD))

    def BINARY_XOR(self, code):
        code.ReadOpcode()
        y = self.stack.pop().GetString(PRECEDENCE_BXOR+1)
        x = self.stack.pop().GetString(PRECEDENCE_BXOR)
        self.stack.append(Expression('%s ^ %s' % (x, y), PRECEDENCE_BXOR))

    def BREAK_LOOP(self, code):
        code.ReadOpcode('BREAK_LOOP')
        self.addline(code.GetLine(), 'break')
        
    def BUILD_LIST(self, code):
        code.ReadOpcode('BUILD_LIST')
        oparg = code.ReadOperand()
        values = []
        for i in range(oparg):
            value = self.stack.pop()
            if value.Precedence() < PRECEDENCE_ARG:
                value = '(%s)' % value
            values.append(str(value))
        values.reverse()
        valuelist = string.join(values, ', ')
        self.stack.append(Expression('[%s]' % valuelist, PRECEDENCE_ATOM))

    def BUILD_MAP(self, code):
        code.ReadOpcode('BUILD_MAP')
        code.ReadOperand()
        self.stack.append(Map())

    def BUILD_SLICE(self, code):
        code.ReadOpcode()
        code.ReadOperand()
        z = self.stack.pop()
        if isinstance(z, Constant) and z.Value() is None:
            z = ''
        else:
            z = z.GetString(PRECEDENCE_ARG)
        y = self.stack.pop()
        if isinstance(y, Constant) and y.Value() is None:
            y = ''
        else:
            y = y.GetString(PRECEDENCE_ARG)
        x = self.stack.pop()
        if isinstance(x, Constant) and x.Value() is None:
            x = ''
        else:
            x = x.GetString(PRECEDENCE_ARG)
        # always goes into BINARY_SUBSCR, so precedence is irrelevant
        self.stack.append(Expression('%s:%s:%s' % (x, y, z), PRECEDENCE_NONE))
        
    def BUILD_TUPLE(self, code):
        code.ReadOpcode()
        oparg = code.ReadOperand()
        values = []
        for i in range(oparg):
            value = self.stack.pop().GetString(PRECEDENCE_ARG)
            values.append(value)
        values.reverse()
        self.stack.append(Tuple(values))

    def CALL_FUNCTION(self, code):
        opcode = code.ReadOpcode('CALL_FUNCTION', 'CALL_FUNCTION_VAR',
                                 'CALL_FUNCTION_KW', 'CALL_FUNCTION_VAR_KW')
        oparg = code.ReadOperand()
        nkw, nargs = divmod(oparg, 256)
        args = []
        if opcode in ('CALL_FUNCTION_KW', 'CALL_FUNCTION_VAR_KW'):
            name = self.stack.pop()
            args.append('**%s' % name)
        if opcode in ('CALL_FUNCTION_VAR', 'CALL_FUNCTION_VAR_KW'):
            name = self.stack.pop()
            args.append('*%s' % name)
        for i in range(nkw):
            value = self.stack.pop().GetString(PRECEDENCE_ARG)
            name = self.stack.pop().Value()
            args.append('%s=%s' % (name, value))
        for i in range(nargs):
            arg = self.stack.pop().GetString(PRECEDENCE_ARG)
            args.append(str(arg))
        args.reverse()
        arglist = string.join(args, ', ')
        func = self.stack.pop().GetString(PRECEDENCE_ATOM)
        self.stack.append(Expression('%s(%s)' % (func, arglist),
                                     PRECEDENCE_ATOM))

    CALL_FUNCTION_VAR = CALL_FUNCTION
    CALL_FUNCTION_KW = CALL_FUNCTION
    CALL_FUNCTION_VAR_KW = CALL_FUNCTION
    
    def COMPARE_OP(self, code):
        code.ReadOpcode()
        oparg = code.ReadOperand()
        if len(self.stack) == 1:
            y = self.stack.pop()
            x = None
        else:
            y = self.stack.pop()
            x = self.stack.pop()
        op = dis.cmp_op[oparg]
        if op[0] in '!<=>':
            prec = PRECEDENCE_CMP
        elif op[-2:] == 'in':
            prec = PRECEDENCE_IN
        else:
            assert op[:2] == 'is', `op`
            prec = PRECEDENCE_IS
        if y.Precedence() <= prec:
            y = '(%s)' % y
        if x is None:
            self.stack.append(Chain('%s %s' % (op, y)))
        else:
            if x.Precedence() < prec:
                x = '(%s)' % x
            self.stack.append(Expression('%s %s %s' % (x, op, y), prec))

    def DELETE_ATTR(self, code):
        code.ReadOpcode()
        oparg = code.ReadOperand()
        attr = code.GetName(oparg)
        x = self.stack.pop().GetString(PRECEDENCE_ATOM)
        self.addline(code.GetLine(), 'del %s.%s' % (x, attr))
        
    def DELETE_FAST(self, code):
        names = []
        lastlineno = -1
        while code.NextOpcode() in ('DELETE_FAST', 'DELETE_GLOBAL',
                                    'DELETE_NAME'):
            opcode = code.ReadOpcode()
            if lastlineno == -1:
                lineno = lastlineno = code.GetLine()
            else:
                lineno = code.GetLine()
            if lineno != lastlineno:
                self.addline(lastlineno, 'del %s' % string.join(names, ', '))
                names = []
                lastlineno = lineno
            oparg = code.ReadOperand()
            if opcode == 'DELETE_FAST':
                names.append(code.GetLocal(oparg))
            elif opcode == 'DELETE_GLOBAL':
                names.append(code.GetName(oparg))
            else:
                assert opcode == 'DELETE_NAME', `opcode`
                names.append(code.GetName(oparg))
        self.addline(lastlineno, 'del %s' % string.join(names, ', '))

    DELETE_GLOBAL = DELETE_FAST
    DELETE_NAME = DELETE_FAST

    def DELETE_SLICE_0(self, code):
        code.ReadOpcode()
        x = self.stack.pop().GetString(PRECEDENCE_ATOM)
        self.addline(code.GetLine(), 'del %s[:]' % x)

    def DELETE_SLICE_1(self, code):
        code.ReadOpcode()
        y = self.stack.pop().GetString(PRECEDENCE_ARG)
        x = self.stack.pop().GetString(PRECEDENCE_ATOM)
        self.addline(code.GetLine(), 'del %s[%s:]' % (x, y))

    def DELETE_SLICE_2(self, code):
        code.ReadOpcode()
        z = self.stack.pop().GetString(PRECEDENCE_ARG)
        x = self.stack.pop().GetString(PRECEDENCE_ATOM)
        self.addline(code.GetLine(), 'del %s[:%s]' % (x, z))
        
    def DELETE_SLICE_3(self, code):
        code.ReadOpcode()
        z = self.stack.pop().GetString(PRECEDENCE_ARG)
        y = self.stack.pop().GetString(PRECEDENCE_ARG)
        x = self.stack.pop().GetString(PRECEDENCE_ATOM)
        self.addline(code.GetLine(), 'del %s[%s:%s]' % (x, y, z))
        
    def DELETE_SUBSCR(self, code):
        code.ReadOpcode()
        y = self.stack.pop().GetString(PRECEDENCE_NONE)
        x = self.stack.pop().GetString(PRECEDENCE_ATOM)
        self.addline(code.GetLine(), 'del %s[%s]' % (x, y))

    def DUP_TOP(self, code):
        code.ReadOpcode('DUP_TOP')
        self.stack.append(self.stack[-1])
        
    def DUP_TOPX(self, code):
        code.ReadOpcode('DUP_TOPX')
        n = code.ReadOperand()
        self.stack = self.stack + self.stack[-n:]
        
    def EXEC_STMT(self, code):
        code.ReadOpcode('EXEC_STMT')
        lineno = code.GetLine()
        locals = self.stack.pop()
        globals = self.stack.pop()
        stmt = self.stack.pop().GetString(PRECEDENCE_IN)
        if isinstance(globals, Constant) and globals.Value() is None:
            self.addline(lineno, 'exec %s' % stmt)
        else:
            if locals is globals:
                globals = globals.GetString(PRECEDENCE_ARG)
                self.addline(lineno, 'exec %s in %s' % (stmt, globals))
            else:
                globals = globals.GetString(PRECEDENCE_ARG)
                locals = locals.GetString(PRECEDENCE_ARG)
                self.addline(lineno,
                             'exec %s in %s, %s' % (stmt, globals, locals))

    def FOR_LOOP(self, code):
        code.ReadOpcode('FOR_LOOP')
        leap = code.ReadOperand()
        loopcleanup = code.GetPosition() + leap
        self.stack.pop()  # sequence index
        forlist = self.stack.pop()
        forvar = self.build_target(code).GetString(PRECEDENCE_NONE)
        head = "for %s in %s:" % (forvar, forlist)
        lineno = code.GetLine()
        d = Decompiler(self.version)
        d.decompile(code, 'JUMP_ABSOLUTE')
        self.addclause(lineno, head, d.getsource(1))
        code.ReadOpcode('JUMP_ABSOLUTE')
        oparg = code.ReadOperand()  # to FOR_LOOP (or SET_LINENO)
        assert code.GetPosition() == loopcleanup
        code.ReadOpcode('POP_BLOCK')
        end = self.loop[1]
        self.loop = None
        if code.GetPosition() < end:
            lineno = code.GetLine()
            code.PushStop(end)
            d = Decompiler(self.version)
            d.decompile(code)
            code.PopStop()
            self.addclause(lineno, "else:", d.getsource(1))
        assert code.GetPosition() == end
        
    def IMPORT_NAME(self, code):
        names = []
        while code.NextOpcode() == 'IMPORT_NAME':
            code.ReadOpcode('IMPORT_NAME')
            if self.version >= (2, 0):
                self.stack.pop()
            oparg = code.ReadOperand()
            module = code.GetName(oparg)
            opname = code.ReadOpcode('IMPORT_FROM', 'IMPORT_STAR',
                                     'STORE_FAST', 'STORE_NAME')
            if opname in ('IMPORT_FROM', 'IMPORT_STAR'):
                if names:
                    self.addline('import %s' % string.join(names, ', '))
                    names = []
                if opname == 'IMPORT_STAR':
                    objs = '*'
                else:
                    while opname == 'IMPORT_FROM':
                        oparg = code.ReadOperand()
                        name1 = code.GetName(oparg)
                        if self.version >= (2, 0):
                            opname = code.ReadOpcode('STORE_FAST', 'STORE_NAME')
                            oparg = code.ReadOperand()
                            if opname == 'STORE_FAST':
                                name2 = code.GetLocal(oparg)
                            else:
                                name2 = code.GetName(oparg)
                        else:
                            name2 = name1
                        if name1 == name2:
                            names.append(name1)
                        else:
                            names.append('%s as %s' % (name1, name2))
                        opname = code.ReadOpcode('IMPORT_FROM', 'POP_TOP')
                    objs = string.join(names, ', ')
                self.addline(code.GetLine(),
                             'from %s import %s' %
                             (module, objs))
                names = []
            else:
                assert opname in ('STORE_FAST', 'STORE_NAME'), `opname`
                oparg = code.ReadOperand()
                if opname == 'STORE_FAST':
                    name = code.GetLocal(oparg)
                else:
                    name = code.GetName(oparg)
                if module == name:
                    names.append(module)
                else:
                    names.append("%s as %s" % (module, name))
        if names:
            self.addline(code.GetLine(),
                         'import %s' % string.join(names, ', '))

    def INPLACE_ADD(self, code):
        opcode = code.ReadOpcode(
            'INPLACE_ADD', 'INPLACE_AND', 'INPLACE_DIVIDE', 'INPLACE_LSHIFT',
            'INPLACE_MODULO', 'INPLACE_MULTIPLY', 'INPLACE_OR', 'INPLACE_POWER',
            'INPLACE_RSHIFT', 'INPLACE_SUBTRACT', 'INPLACE_XOR')
        if opcode == 'INPLACE_ADD':
            op = '+='
        elif opcode == 'INPLACE_AND':
            op = '&='
        elif opcode == 'INPLACE_DIVIDE':
            op = '/='
        elif opcode == 'INPLACE_LSHIFT':
            op = '<<='
        elif opcode == 'INPLACE_MODULO':
            op = '%='
        elif opcode == 'INPLACE_MULTIPLY':
            op = '*='
        elif opcode == 'INPLACE_OR':
            op = '|='
        elif opcode == 'INPLACE_POWER':
            op = '**='
        elif opcode == 'INPLACE_RSHIFT':
            op = '>>='
        elif opcode == 'INPLACE_SUBTRACT':
            op = '-='
        else:
            assert opcode == 'INPLACE_XOR', `opcode`
            op = '^='
        y = self.stack.pop().GetString(PRECEDENCE_NONE)
        x = self.stack.pop().GetString(PRECEDENCE_NONE)
        opcode = code.ReadOpcode('ROT_THREE', 'ROT_TWO', 'STORE_FAST',
                                 'STORE_GLOBAL')
        if opcode == 'STORE_FAST':
            code.ReadOperand()
        elif opcode == 'STORE_GLOBAL':
            code.ReadOperand()
        elif opcode == 'STORE_NAME':
            code.ReadOperand()
        elif opcode == 'ROT_THREE':
            code.ReadOpcode('STORE_SUBSCR')
            self.stack.pop()
            self.stack.pop()
        elif opcode == 'ROT_TWO':
            code.ReadOpcode('STORE_ATTR')
            code.ReadOperand()
            self.stack.pop()
        self.addline(code.GetLine(), '%s %s %s' % (x, op, y))

    INPLACE_AND = INPLACE_ADD
    INPLACE_DIVIDE = INPLACE_ADD
    INPLACE_LSHIFT = INPLACE_ADD
    INPLACE_MODULO = INPLACE_ADD
    INPLACE_MULTIPLY = INPLACE_ADD
    INPLACE_OR = INPLACE_ADD
    INPLACE_POWER = INPLACE_ADD
    INPLACE_RSHIFT = INPLACE_ADD
    INPLACE_SUBTRACT = INPLACE_ADD
    INPLACE_XOR = INPLACE_ADD
    
    def JUMP_ABSOLUTE(self, code):
        code.ReadOpcode('JUMP_ABSOLUTE')
        code.ReadOperand()
        self.addline(code.GetLine(), 'continue')
        
    def JUMP_IF_FALSE(self, code):
        code.ReadOpcode('JUMP_IF_FALSE')
        leap = code.ReadOperand()
        endcond = code.GetPosition() + leap
        opcode = code.ReadOpcode('POP_TOP')
        assert opcode == 'POP_TOP', `opcode`
        lineno = code.GetLine()
        code.PushStop(endcond)
        d = Decompiler(self.version)
        if self.loop is None:
            d.decompile(code, 'JUMP_FORWARD')
        else:
            d.decompile(code, 'JUMP_ABSOLUTE')
        code.PopStop()
        stack = d.getstack()
        if stack:
            if len(stack) == 1:
                assert code.GetPosition() == endcond
                # and
                x = self.stack.pop().GetString(PRECEDENCE_AND+1)
                y = stack.pop().GetString(PRECEDENCE_AND)
                self.stack.append(
                    Expression('%s and %s' % (x, y), PRECEDENCE_AND))
            else:
                # assert
                self.stack.pop()
                test = stack.pop().GetString(PRECEDENCE_ARG)
                value = stack.pop()
                if value is None:
                    self.addline(lineno, 'assert %s' % test)
                else:
                    value = value.GetString(PRECEDENCE_ARG)
                    self.addline(lineno, 'assert %s, %s' % (test, value))
                code.ReadOpcode('POP_TOP')
        else:
            condition = self.stack.pop()
            body = d.getsource(1)
            if self.loop is None:
                # if
                self.addclause(lineno, 'if %s:' % condition, body)
                code.ReadOpcode('JUMP_FORWARD')
                leap = code.ReadOperand()
                end = code.GetPosition() + leap
                code.ReadOpcode('POP_TOP')
                while code.GetPosition() < end:
                    lineno = code.GetLine()
                    code.PushStop(end)
                    d = Decompiler(self.version)
                    d.decompile(code, 'JUMP_FORWARD')
                    code.PopStop()
                    body = d.getsource(1)
                    if body.has_key(lineno):
                        if body[lineno][-1] == ':':
                            # elif
                            body = d.getsource(0)
                            body[lineno] = 'el' + body[lineno]
                            self.lines.update(body)
                        else:
                            #assert len(body) == 1, `body`
                            line = body[lineno]
                            self.addline(lineno, "else: %s" %
                                         string.strip(line))
                            del body[lineno]
                            self.lines.update(body)
                            body[lineno] = line
                    else:
                        self.addline(lineno, "else:")
                        self.lines.update(body)
                    code.SetLine(max(body.keys()) + 1)
            else:
                # while
                self.addclause(lineno, "while %s:" % condition, body)
                code.ReadOpcode('JUMP_ABSOLUTE')
                oparg = code.ReadOperand()
                assert oparg == self.loop[0], `(oparg, self.loop)`
                code.ReadOpcode('POP_TOP')
                code.ReadOpcode('POP_BLOCK')
                end = self.loop[1]
                self.loop = None
                if code.GetPosition() < end:
                    lineno = code.GetLine()
                    code.PushStop(end)
                    d = Decompiler(self.version)
                    d.decompile(code)
                    code.PopStop()
                    self.addclause(lineno, "else:", d.getsource(1))
            assert code.GetPosition() == end

    def JUMP_IF_TRUE(self, code):
        code.ReadOpcode('JUMP_IF_TRUE')
        leap = code.ReadOperand()
        end = code.GetPosition() + leap
        code.ReadOpcode('POP_TOP')
        code.PushStop(end)
        d = Decompiler(self.version)
        d.decompile(code, 'RAISE_VARARGS')
        code.PopStop()
        stack = d.getstack()
        assert stack
        if code.GetPosition() == end:
            # or expression
            x = self.stack.pop().GetString(PRECEDENCE_OR+1)
            y = stack.pop().GetString(PRECEDENCE_OR)
            self.stack.append(Expression('%s or %s' % (x, y), PRECEDENCE_OR))
        else:
            # raise AssertionError, exp
            test = self.stack.pop()
            code.ReadOpcode('RAISE_VARARGS')
            oparg = code.ReadOperand()
            if oparg == 1:
                self.stack.append(None)
            else:
                value = stack.pop()
                self.stack.append(value)
            self.stack.append(test)
            assert len(self.stack) == 2, `self.stack`
        assert code.GetPosition() == end

    def LOAD_ATTR(self, code):
        code.ReadOpcode('LOAD_ATTR')
        oparg = code.ReadOperand()
        attr = code.GetName(oparg)
        x = self.stack.pop()
        if x.Precedence() < PRECEDENCE_ATOM:
            x = '(%s)' % x
        self.stack.append(Expression('%s.%s' % (x, attr), PRECEDENCE_ATOM))
        
    def LOAD_CONST(self, code):
        code.ReadOpcode('LOAD_CONST')
        oparg = code.ReadOperand()
        self.stack.append(Constant(code.GetConstant(oparg)))

    def LOAD_FAST(self, code):
        code.ReadOpcode('LOAD_FAST')
        oparg = code.ReadOperand()
        self.stack.append(Local(code.GetLocal(oparg)))
        
    def LOAD_GLOBAL(self, code):
        code.ReadOpcode('LOAD_GLOBAL')
        oparg = code.ReadOperand()
        self.stack.append(Global(code.GetName(oparg)))

    def LOAD_LOCALS(self, code):
        code.ReadOpcode('LOAD_LOCALS')
        self.stack.append(Constant(None))
        
    def LOAD_NAME(self, code):
        code.ReadOpcode('LOAD_NAME')
        oparg = code.ReadOperand()
        self.stack.append(Local(code.GetName(oparg)))

    def MAKE_FUNCTION(self, code):
        code.ReadOpcode('MAKE_FUNCTION')
        defaultcount = code.ReadOperand()
        co = self.stack.pop().Value()
        if co.co_name == '<lambda>':
            # lambda
            # Get the function def part
            params = []
            argcount = co.co_argcount
            while argcount:
                argcount = argcount - 1
                name = co.co_varnames[argcount]
                if defaultcount:
                    defaultcount = defaultcount - 1
                    default = self.stack.pop().GetString(PRECEDENCE_ARG)
                    params.append('%s=%s' % (name, default))
                else:
                    params.append(name)
            params.reverse()
            argcount = co.co_argcount
            if co.co_flags & VARARGS:
                params.append('*' + co.co_varnames[argcount])
                argcount = argcount + 1
            if co.co_flags & KWARGS:
                params.append('**' + co.co_varnames[argcount])
            paramlist = string.join(params, ', ')
            # get the function body
            d = Decompiler(self.version)
            d.decompile(CodeCursor(co), 'RETURN_VALUE')
            stack = d.getstack()
            assert len(stack) == 1, `stack`
            y = stack.pop().GetString(PRECEDENCE_LAMBDA)
            self.stack.append(
                Expression('lambda %s: %s' % (paramlist, y), PRECEDENCE_LAMBDA))
        else:
            opcode = code.ReadOpcode('CALL_FUNCTION', 'STORE_FAST',
                                     'STORE_NAME')
            if opcode == 'CALL_FUNCTION':
                # class
                oparg = code.ReadOperand()
                assert oparg == 0, `oparg`
                code.ReadOpcode('BUILD_CLASS')
                super = self.stack.pop().Value()
                name = self.stack.pop().Value()
                opcode = code.ReadOpcode('STORE_FAST', 'STORE_NAME')
                oparg = code.ReadOperand()
                if opcode == 'STORE_FAST':
                    classname = code.GetLocal(oparg)
                else:
                    classname = code.GetName(oparg)
                assert name == classname, `name, classname`
                if super:
                    classname = '%s(%s)' % (classname, string.join(super, ', '))
                lineno = code.GetLine()
                d = Decompiler(self.version)
                d.decompile(CodeCursor(co))
                body = d.getsource(1)
                if body.has_key(lineno):
                    if len(body) == 1:
                        self.addline(lineno, "class %s: %s" % (classname,
                                      string.strip(body[lineno])))
                    else:
                        assert 0
                        # __doc__ string appears in 0th row
                        assert not body.has_key(lineno+1), `body`
                        body[lineno+1] = body[lineno]
                        del body[lineno]
                        self.addline(lineno, "class %s:" % classname)
                        self.lines.update(body)
                else:
                    self.addline(lineno, "class %s:" % classname)
                    self.lines.update(body)
                code.SetLine(max(body.keys()) + 1)
            else:
                assert opcode in ('STORE_FAST', 'STORE_NAME'), `opcode`
                # def
                oparg = code.ReadOperand()
                if opcode == 'STORE_FAST':
                    funcname = code.GetLocal(oparg)
                else:
                    funcname = code.GetName(oparg)
                # Get the function def part
                params = []
                argcount = co.co_argcount
                while argcount:
                    argcount = argcount - 1
                    name = co.co_varnames[argcount]
                    if defaultcount:
                        defaultcount = defaultcount - 1
                        default = self.stack.pop()
                        if default.Precedence() < PRECEDENCE_ARG:
                            default = '(%s)' % default
                        params.append('%s=%s' % (name, default))
                    else:
                        params.append(name)
                params.reverse()
                argcount = co.co_argcount
                if co.co_flags & VARARGS:
                    params.append('*' + co.co_varnames[argcount])
                    argcount = argcount + 1
                if co.co_flags & KWARGS:
                    params.append('**' + co.co_varnames[argcount])
                paramlist = string.join(params, ', ')
                head = "def %s(%s):" % (funcname, paramlist)
                # get the function body
                lineno = code.GetLine()
                d = Decompiler(self.version)
                d.decompile(CodeCursor(co))
                self.addclause(lineno, head, d.getsource(1))

    def PRINT_ITEM(self, code):
        code.ReadOpcode('PRINT_ITEM')
        x = self.stack.pop().GetString(PRECEDENCE_ARG)
        if code.NextOpcode() == 'PRINT_NEWLINE':
            code.ReadOpcode('PRINT_NEWLINE')
            self.addline(code.GetLine(), 'print %s' % x)
        else:
            self.addline(code.GetLine(), 'print %s,' % x)

    def PRINT_ITEM_TO(self, code):
        # XXX - if file is an expression, it gets evaluated multiple times.
        code.ReadOpcode('PRINT_ITEM_TO')
        file = self.stack.pop()
        x = self.stack.pop().GetString(PRECEDENCE_ARG)
        if code.NextOpcode() == 'PRINT_NEWLINE_TO' and self.stack[-1] is file:
            code.ReadOpcode('PRINT_NEWLINE_TO')
            self.stack.pop()
            if file.Precedence() < PRECEDENCE_ARG:
                file = '(%s)' % file
            self.addline('print >> %s, %s' % (file, x))
        else:
            if file.Precedence() < PRECEDENCE_ARG:
                file = '(%s)' % file
            self.addline('print >> %s, %s,' % (file, x))

    def PRINT_NEWLINE(self, code):
        code.ReadOpcode('PRINT_NEWLINE')
        self.addline(code.GetLine(), 'print')
        
    def PRINT_NEWLINE_TO(self, code):
        code.ReadOpcode('PRINT_NEWLINE')
        file = self.stack.pop().GetString(PRECEDENCE_ARG)
        self.addline(code.GetLine(), 'print >> %s' % file)
        
    def POP_TOP(self, code):
        code.ReadOpcode('POP_TOP')
        self.addline(code.GetLine(),
                     self.stack.pop().GetString(PRECEDENCE_NONE))

    def RAISE_VARARGS(self, code):
        code.ReadOpcode('RAISE_VARARGS')
        argcount = code.ReadOperand()
        args = []
        for i in range(argcount):
            arg = self.stack.pop().GetString(PRECEDENCE_ARG)
            args.append(arg)
        args.reverse()
        self.addline(code.GetLine(), 'raise %s' % string.join(args, ', '))
        
    def RETURN_VALUE(self, code):
        code.ReadOpcode()
        y = self.stack.pop()
        if isinstance(y, Constant) and y.Value() is None:
            if not code.AtEnd():
                self.addline(code.GetLine(), 'return')
        else:
            value = y.GetString(PRECEDENCE_NONE)
            self.addline(code.GetLine(), 'return %s' % value)

    def ROT_THREE(self, code):
        code.ReadOpcode('ROT_THREE')
        assert len(self.stack) >= 3, `code.GetPosition(), self.stack`
        self.stack.pop()  # duplicate of y
        y = self.stack.pop().GetString(PRECEDENCE_CMP+1)
        x = self.stack.pop().GetString(PRECEDENCE_CMP+1)
        code.ReadOpcode('COMPARE_OP')
        oparg = code.ReadOperand()
        op = dis.cmp_op[oparg]
        chain = '%s %s %s' % (x, op, y)
        opcode = code.ReadOpcode('JUMP_IF_FALSE')
        leap = code.ReadOperand()
        stop1 = code.GetPosition() + leap
        while opcode == 'JUMP_IF_FALSE':
            assert code.GetPosition() + leap == stop1, \
                   `code.GetPosition(), leap, stop1`
            code.ReadOpcode('POP_TOP')
            code.PushStop(stop1 - 6)
            d = Decompiler(self.version)
            d.decompile(code, 'ROT_THREE')
            code.PopStop()
            stack = d.getstack()
            y = stack.pop().GetString(PRECEDENCE_CMP+1)
            opcode = code.ReadOpcode('COMPARE_OP', 'ROT_THREE')
            if opcode == 'ROT_THREE':
                opcode = code.ReadOpcode('COMPARE_OP')
            oparg = code.ReadOperand()
            op = dis.cmp_op[oparg]
            chain = '%s %s %s' % (chain, op, y)
            opcode = code.ReadOpcode('JUMP_IF_FALSE', 'JUMP_FORWARD')
            leap = code.ReadOperand()
        assert leap == 2, `leap`
        assert code.GetPosition() == stop1, `code.GetPosition(), stop1`
        code.ReadOpcode('ROT_TWO')
        code.ReadOpcode('POP_TOP')
        self.stack.append(Expression(chain, PRECEDENCE_CMP))

    def ROT_TWO(self, code):
        code.ReadOpcode('ROT_TWO')
        n1 = self.stack.pop()
        n2 = self.stack.pop()
        self.stack.append(n1)
        self.stack.append(n2)

    def handle_except_clause(self, code):
        opcode = code.ReadOpcode('DUP_TOP', 'POP_TOP', 'SET_LINENO')
        if opcode == 'SET_LINENO':
            code.ReadOperand()
            opcode = code.ReadOpcode('DUP_TOP', 'POP_TOP')
        lineno = code.GetLine()
        if opcode == 'DUP_TOP':
            d = Decompiler(self.version)
            d.decompile(code, 'COMPARE_OP')
            stack = d.getstack()
            exc_type = stack.pop().GetString(PRECEDENCE_ARG)
            code.ReadOpcode('COMPARE_OP')
            oparg = code.ReadOperand()
            assert oparg == 10, `oparg`  # 10 -> exception match
            code.ReadOpcode('JUMP_IF_FALSE')
            leap = code.ReadOperand()
            nextclause = code.GetPosition() + leap
            code.ReadOpcode('POP_TOP')  # result of test
            code.ReadOpcode('POP_TOP')  # exc_type
            opcode = code.NextOpcode()
            if opcode == 'POP_TOP':  # exc_value
                code.ReadOpcode('POP_TOP')
                head = 'except %s:' % exc_type
            else:
                exc_value = self.build_target(code).GetString(PRECEDENCE_ARG)
                head = 'except %s, %s:' % (exc_type, exc_value)
        else:
            code.ReadOpcode('POP_TOP')  # exc_value
            head = 'except:'
            nextclause = None
        code.ReadOpcode('POP_TOP')  # exc_tb
        d = Decompiler(self.version)
        d.decompile(code, 'JUMP_FORWARD')
        self.addclause(lineno, head, d.getsource(1))
        code.ReadOpcode('JUMP_FORWARD')
        leap = code.ReadOperand()
        end = code.GetPosition() + leap
        if nextclause is not None:
            assert code.GetPosition() == nextclause
            code.ReadOpcode('POP_TOP')
        return end
        
    def SETUP_EXCEPT(self, code):
        code.ReadOpcode('SETUP_EXCEPT')
        leap = code.ReadOperand()
        firstexceptclause = code.GetPosition() + leap
        lineno = code.GetLine()
        d = Decompiler(self.version)
        d.decompile(code, 'POP_BLOCK')
        self.addclause(lineno, "try:", d.getsource(1))
        code.ReadOpcode('POP_BLOCK')
        code.ReadOpcode('JUMP_FORWARD')
        leap = code.ReadOperand()
        elseclause = code.GetPosition() + leap
        assert code.GetPosition() == firstexceptclause
        end = self.handle_except_clause(code)
        while code.NextOpcode() != 'END_FINALLY':
            end1 = self.handle_except_clause(code)
            assert end1 == end, `end1, end`
        code.ReadOpcode('END_FINALLY')
        assert code.GetPosition() == elseclause, \
               `code.GetPosition(), elseclause`
        if elseclause < end:
            lineno = code.GetLine()
            code.PushStop(end)
            d = Decompiler(self.version)
            d.decompile(code)
            code.PopStop()
            self.addclause(lineno, "else:", d.getsource(1))
        assert code.GetPosition() == end
        
    def SETUP_FINALLY(self, code):
        code.ReadOpcode('SETUP_FINALLY')
        leap = code.ReadOperand()
        finallyclause = code.GetPosition() + leap
        lineno = code.GetLine()
        d = Decompiler(self.version)
        d.decompile(code, 'POP_BLOCK')
        body = d.getsource(1)
        self.addclause(lineno, "try:", body)
        code.ReadOpcode('POP_BLOCK')
        code.ReadOpcode('LOAD_CONST')
        oparg = code.ReadOperand()
        assert oparg == 0, `oparg`
        assert code.GetPosition() == finallyclause
        lineno = code.GetLine()
        d = Decompiler(self.version)
        d.decompile(code, 'END_FINALLY')
        body = d.getsource(1)
        self.addclause(lineno, "finally:", body)
        code.ReadOpcode('END_FINALLY')
       
    def SETUP_LOOP(self, code):
        code.ReadOpcode('SETUP_LOOP')
        leap = code.ReadOperand()
        assert self.loop is None, `self.loop`
        i = code.GetPosition()
        self.loop = i, i + leap

    def SLICE_0(self, code):
        code.ReadOpcode()
        x = self.stack.pop().GetString(PRECEDENCE_ATOM)
        self.stack.append(Expression('%s[:]' % x, PRECEDENCE_ATOM))

    def SLICE_1(self, code):
        code.ReadOpcode()
        y = self.stack.pop().GetString(PRECEDENCE_ARG)
        x = self.stack.pop().GetString(PRECEDENCE_ATOM)
        self.stack.append(Expression('%s[%s:]' % (x, y), PRECEDENCE_ATOM))

    def SLICE_2(self, code):
        code.ReadOpcode()
        z = self.stack.pop().GetString(PRECEDENCE_ARG)
        x = self.stack.pop().GetString(PRECEDENCE_ATOM)
        self.stack.append(Expression('%s[:%s]' % (x, z), PRECEDENCE_ATOM))
        
    def SLICE_3(self, code):
        code.ReadOpcode()
        z = self.stack.pop().GetString(PRECEDENCE_ARG)
        y = self.stack.pop().GetString(PRECEDENCE_ARG)
        x = self.stack.pop().GetString(PRECEDENCE_ATOM)
        self.stack.append(Expression('%s[%s:%s]' % (x, y, z), PRECEDENCE_ATOM))
        
    def STORE_ATTR(self, code):
        code.ReadOpcode()
        oparg = code.ReadOperand()
        attr = code.GetName(oparg)
        name = self.stack.pop().GetString(PRECEDENCE_ATOM)
        value = self.stack.pop().GetString(PRECEDENCE_NONE)
        self.addline(code.GetLine(), '%s.%s = %s' % (name, attr, value))

    def STORE_FAST(self, code):
        code.ReadOpcode()
        oparg = code.ReadOperand()
        name = code.GetLocal(oparg)
        value = self.stack.pop().GetString(PRECEDENCE_NONE)
        self.addline(code.GetLine(), '%s = %s' % (name, value))

    def STORE_GLOBAL(self, code):
        # XXX - need to put in global statement
        code.ReadOpcode()
        oparg = code.ReadOperand()
        name = code.GetName(oparg)
        value = self.stack.pop().GetString(PRECEDENCE_NONE)
        self.addline(code.GetLine(), '%s = %s' % (name, value))

    def STORE_NAME(self, code):
        code.ReadOpcode()
        oparg = code.ReadOperand()
        name = code.GetName(oparg)
        value = self.stack.pop().GetString(PRECEDENCE_NONE)
        self.addline(code.GetLine(), '%s = %s' % (name, value))

    def STORE_SLICE_0(self, code):
        code.ReadOpcode()
        x = self.stack.pop().GetString(PRECEDENCE_ATOM)
        value = self.stack.pop().GetString(PRECEDENCE_NONE)
        self.addline(code.GetLine(), '%s[:] = %s' % (x, value))

    def STORE_SLICE_1(self, code):
        code.ReadOpcode()
        y = self.stack.pop().GetString(PRECEDENCE_ARG)
        x = self.stack.pop().GetString(PRECEDENCE_ATOM)
        value = self.stack.pop().GetString(PRECEDENCE_NONE)
        self.addline(code.GetLine(), '%s[%s:] = %s' % (x, y, value))

    def STORE_SLICE_2(self, code):
        code.ReadOpcode()
        z = self.stack.pop().GetString(PRECEDENCE_ARG)
        x = self.stack.pop().GetString(PRECEDENCE_ATOM)
        value = self.stack.pop().GetString(PRECEDENCE_NONE)
        self.addline(code.GetLine(), '%s[:%s] = %s' % (x, z, value))
        
    def STORE_SLICE_3(self, code):
        code.ReadOpcode()
        z = self.stack.pop().GetString(PRECEDENCE_ARG)
        y = self.stack.pop().GetString(PRECEDENCE_ARG)
        x = self.stack.pop().GetString(PRECEDENCE_ATOM)
        value = self.stack.pop().GetString(PRECEDENCE_NONE)
        self.addline(code.GetLine(), '%s[%s:%s] = %s' % (x, y, z, value))
        
    def STORE_SUBSCR(self, code):
        code.ReadOpcode()
        key = self.stack.pop()
        obj = self.stack.pop()
        if isinstance(obj, Map):
            value = self.stack.pop().GetString(PRECEDENCE_ARG)
            if key.Precedence() < PRECEDENCE_ARG:
                key = '(%s)' % key
            obj.SetAttr(key, value)
        else:
            obj = obj.GetString(PRECEDENCE_ATOM)
            value = self.stack.pop().GetString(PRECEDENCE_NONE)
            self.addline(code.GetLine(),
                         '%s[%s] = %s' % (obj, key, value))

    def UNARY_CONVERT(self, code):
        code.ReadOpcode()
        value = self.stack.pop().GetString(PRECEDENCE_NONE)
        self.stack.append(Expression('`%s`' % value, PRECEDENCE_ATOM))
        
    def UNARY_INVERT(self, code):
        code.ReadOpcode()
        # only requires PRECEDENCE_UNARY, but both powers and other
        # unary operators are confusing without parentheses
        y = self.stack.pop().GetString(PRECEDENCE_ATOM)
        self.stack.append(Expression('~%s' % y, PRECEDENCE_UNARY))

    def UNARY_NEGATIVE(self, code):
        code.ReadOpcode()
        # only requires PRECEDENCE_UNARY, but both powers and other
        # unary operators are confusing without parentheses
        y = self.stack.pop().GetString(PRECEDENCE_ATOM)
        self.stack.append(Expression('-%s' % y, PRECEDENCE_UNARY))

    def UNARY_NOT(self, code):
        code.ReadOpcode()
        y = self.stack.pop().GetString(PRECEDENCE_NOT)
        self.stack.append(Expression('not %s' % y, PRECEDENCE_NOT))

    def UNARY_POSITIVE(self, code):
        code.ReadOpcode()
        # only requires PRECEDENCE_UNARY, but both powers and other
        # unary operators are confusing without parentheses
        y = self.stack.pop().GetString(PRECEDENCE_ATOM)
        self.stack.append(Expression('+%s' % y, PRECEDENCE_UNARY))

    def build_target(self, code):
        if code.NextOpcode() not in ('STORE_FAST', 'STORE_GLOBAL', 'STORE_NAME',
                                     'UNPACK_SEQUENCE', 'UNPACK_TUPLE'):
            d = Decompiler(self.version)
            d.decompile(code, 'STORE_ATTR', 'STORE_SLICE+0', 'STORE_SLICE+1',\
                        'STORE_SLICE+2', 'STORE_SLICE+3', 'STORE_SUBSCR')
        opcode = code.ReadOpcode()
        if opcode == 'STORE_ATTR':
            stack = d.getstack()
            assert len(stack) == 1, `stack`
            name = stack.pop().GetString(PRECEDENCE_ATOM)
            oparg = code.ReadOperand()
            attr = code.GetName(oparg)
            target = Expression('%s.%s' % (name, attr), PRECEDENCE_ATOM)
        elif opcode == 'STORE_FAST':
            oparg = code.ReadOperand()
            target = Local(code.GetLocal(oparg))
        elif opcode == 'STORE_GLOBAL':
            oparg = code.ReadOperand()
            target = Global(code.GetName(oparg))
        elif opcode == 'STORE_NAME':
            oparg = code.ReadOperand()
            target = Local(code.GetName(oparg))
        elif opcode == 'STORE_SLICE+0':
            stack = d.getstack()
            assert len(stack) == 1, `stack`
            x = stack.pop().GetString(PRECEDENCE_ATOM)
            target = Expression('%s[:]' % x, PRECEDENCE_ATOM)
        elif opcode == 'STORE_SLICE+1':
            stack = d.getstack()
            assert len(stack) == 2, `stack`
            y = stack.pop().GetString(PRECEDENCE_ARG)
            x = stack.pop().GetString(PRECEDENCE_ATOM)
            target = Expression('%s[%s:]' % (x, y), PRECEDENCE_ATOM)
        elif opcode == 'STORE_SLICE+2':
            stack = d.getstack()
            assert len(stack) == 2, `stack`
            z = stack.pop().GetString(PRECEDENCE_ARG)
            x = stack.pop().GetString(PRECEDENCE_ATOM)
            target = Expression('%s[:%s]' % (x, z), PRECEDENCE_ATOM)
        elif opcode == 'STORE_SLICE+3':
            stack = d.getstack()
            assert len(stack) == 3, `stack`
            z = stack.pop().GetString(PRECEDENCE_ARG)
            y = stack.pop().GetString(PRECEDENCE_ARG)
            x = stack.pop().GetString(PRECEDENCE_ATOM)
            target = Expression('%s[%s:%s]' % (x, y, z), PRECEDENCE_ATOM)
        elif opcode == 'STORE_SUBSCR':
            stack = d.getstack()
            assert len(stack) == 2, `stack`
            key = stack.pop().GetString(PRECEDENCE_NONE)
            name = stack.pop().GetString(PRECEDENCE_ATOM)
            target = Expression('%s[%s]' % (name, key), PRECEDENCE_ATOM)
        else:
            assert opcode in ('UNPACK_SEQUENCE', 'UNPACK_TUPLE'), `opcode`
            count = code.ReadOperand()
            values = []
            while count > 0:
                value = self.build_target(code).GetString(PRECEDENCE_ARG)
                values.append(value)
                count = count - 1
            target = Tuple(values)
        return target

    def UNPACK_SEQUENCE(self, code):
        seq = self.build_target(code).GetString(PRECEDENCE_NONE)
        rhs = self.stack.pop().GetString(PRECEDENCE_NONE)
        self.addline(code.GetLine(), '%s = %s' % (seq, rhs))
    
    UNPACK_TUPLE = UNPACK_SEQUENCE

# These tests need to be more complete, however, the things that are
# known to be broken are represented
tests = [
    '3\n'           # constant expression
    'a\n'           # name expression
    'a[3][4]\n'     # subscr expression
    'a.b.c\n'       # attr expression
    'a(b, c, d=3, e="d")\n', # function call
    'a = b\n',      # simple assignment
    'a.b.c.d = 2\n',  # attr target
    'a[b][c][d] = 3\n', # subscr target
    'a[:] = 4\n',  # slice targets
    'a[b:] = 5\n',
    'a[:b] = 6\n',
    'a[b:c] = 7\n',
    'a, b, c.d, e[f], g[:], h[i:], j[:k], l[m:n] = z\n', # tuple target
    '(a, b), (c, (d, e)) = t\n', # nested tuple target
    'import spam',
    'import string, spam as ham, sys',
    'from spam import ham, eggs',
    'import spam.ham',    # BROKEN: this type of import
    'from package.spam import ham, eggs as milk',
    'from string import *',
    'def f(a, (b, c)):\n    del f\n', # BROKEN: tuple func args
    'a = b.d = c[3] = a, b = f()',    # BROKEN: chained assignment
    'print >> file, a, b',
    'a = [2*i for i in x]',           # BROKEN: list comprehension
    'if 1:\n  pass\nelif 2: pass\nelse: 3', # BROKEN, swap conditions JUMP_IF_FALSE
    
##    for i in r:
##        print
##    print hello, b
##    a &= 3; b^=9
##    c|=8 ; d <<=2
##    def g(a, b, c=5, d=10, *args, **kw):
##        pass
##    class G(foo):
##        def __init__(self, b=5):
##            "hello"
##            x.k = x.k & (7 * (3 + 4))
##            return x
##    x, y[5][g+4], z.x = 1, 2, 3
##    f(a, b, x=1, **args)
##    try: 1
##    finally: 2
##    if a < b*2 <= c > d:
##        print
##    x = lambda y: (2 * y, 3)
##    class C: pass
##    if 3:
##        print
##    elif 5:
##        del e
##    else:
##        print
##    import sys
##    if 3:
##        print
##    else:
##        i = j + -2 ** -3 ** -2
##        if stuff[0] == '!':
##            stuff = '[^' + stuff[1:] + ']'
##        elif stuff == 'g':
##            stuff = '\\^'
##        else:
##            while stuff[0] == '^':
##                stuff = stuff[1:] + stuff[0]
##            stuff = ('[' + stuff + ']'),
##            
##    a, b, c.b, a[p] = c
##    x = 1 - 2 + 3 - (4 + 5) - 6, 6
##    try:
##        print 2
##    except RuntimeError, exc:
##        del a
##    except IOError:
##        del g
##    except:
##        del b
##    else:
##        del elses
##    if a and b and c:
##        del a
##    if (a and b) and c:
##        del b
##    if a and (b and c):
##        del c
    ]

def test():
    import traceback
    for osrc in tests:
        code1 = compile(osrc, '<string>', 'exec')
        d = Decompiler((2, 0))
        try:
            d.decompile(CodeCursor(code1))
        except:
            print osrc
            print 'FAILS'
            traceback.print_exc(file=sys.stdout)
            print '---'
            continue
        source = d.getsource(0)
        lastline = max(source.keys())
        lines = []
        for lineno in range(1, lastline+2):
            lines.append(source.get(lineno, ''))
        dsrc = string.join(lines, '\n')
        if dsrc == osrc:
            continue
        try:
            code2 = compile(dsrc, '<string>', 'exec')
        except SyntaxError:
            code2 = None
        if code2 and code2.co_code == code1.co_code:
            continue
        print osrc
        print 'BECOMES'
        print dsrc
        print '---'

def f():
    a(b=3, d=3)
    a[x:], b[:] = 1
    # don't work:
##    import spam.ham
##    def f(a, (b, c)):
##        del f
##    a = b.d = c[3] = a, b = f()
##    a = [2*i for i in x]
    
##    import string, x as y
##    from spam.ham import eggs, foo as bar
##    from d import *
##    for i in r:
##        print
    print hello, b
##    a &= 3; b^=9
##    c|=8 ; d <<=2
##    def g(a, b, c=5, d=10, *args, **kw):
##        pass
##    class G(foo):
##        def __init__(self, b=5):
##            "hello"
##            x.k = x.k & (7 * (3 + 4))
##            return x
##    x, y[5][g+4], z.x = 1, 2, 3
##    f(a, b, x=1, **args)
##    try: 1
##    finally: 2
##    if a < b*2 <= c > d:
##        print
##    x = lambda y: (2 * y, 3)
##    class C: pass
##    if 3:
##        print
##    elif 5:
##        del e
##    else:
##        print
##    import sys
##    if 3:
##        print
##    else:
##        i = j + -2 ** -3 ** -2
##        if stuff[0] == '!':
##            stuff = '[^' + stuff[1:] + ']'
##        elif stuff == 'g':
##            stuff = '\\^'
##        else:
##            while stuff[0] == '^':
##                stuff = stuff[1:] + stuff[0]
##            stuff = ('[' + stuff + ']'),
##            
##    a, b, c.b, a[p] = c
##    x = 1 - 2 + 3 - (4 + 5) - 6, 6
##    try:
##        print 2
##    except RuntimeError, exc:
##        del a
##    except IOError:
##        del g
##    except:
##        del b
##    else:
##        del elses
##    if a and b and c:
##        del a
##    if (a and b) and c:
##        del b
##    if a and (b and c):
##        del c
        
if __name__ == '__main__':
  if 1:
    test()
  else:
    out = open(r'E:\output.txt', 'wt')
    try:
        stdout = sys.stdout
        sys.stdout = out
        if 1:
            import marshal
            m = open(r'C:\Python20\Lib\code.pyc', 'rb')
            magic = m.read(4)
            if magic == '\207\306\015\012':
                version = (2, 0)
            elif magic == '\231N\015\012':
                version = (1, 5, 2)
            else:
                raise RuntimeError, 'unrecognised magic: %s' % `magic`
            timestamp = m.read(4)
            s = m.read()
            code = marshal.loads(s)
            m.close()
        else:
            version = (2, 0)
            print f.func_code.co_names
            print f.func_code.co_varnames
            print f.func_code.co_consts
            code = f.func_code
        c = CodeCursor(code)
        d = Decompiler(version)
        d.decompile(c)
        lines = d.getsource(0)
        keys = lines.keys()
        keys.sort()
        for lineno in range(keys[0], keys[-1] + 1):
            print '%4d %s' % (lineno, lines.get(lineno, ''))
        print
        sys.stdout = stdout
    finally:
        out.close()
    sys.stderr.write('DONE\n')
    
