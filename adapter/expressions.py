import logging
import keyword
import re
import operator
import lldb

log = logging.getLogger('expressions')

classify_type = lambda sbtype: None


class PyEvalContext(dict):
    def __init__(self, sbframe):
        self.sbframe = sbframe

    def __missing__(self, name):
        val = self.sbframe.FindVariable(name)
        if not val.IsValid():
            val = self.sbframe.FindValue(name, lldb.eValueTypeRegister)
        if val.IsValid():
            val = Value(val)
            self.__setitem__(name, val)
            return val
        else:
            raise KeyError(name)


class Value(object):
    def __init__(self, sbvalue):
        self.sbvalue = sbvalue
        classify_type(sbvalue.GetType())

    def __nonzero__(self):
        return self.sbvalue.__nonzero__()

    def __str__(self):
        return str(get_value(self))

    def __repr__(self):
        return 'Value(' + str(get_value(self)) + ')'

    def __getitem__(self, key):
        # Allow array access if this value has children...
        if type(key) is Value:
            key = int(key)
        if type(key) is int:
            child_sbvalue = (self.sbvalue.GetValueForExpressionPath("[%i]" % key))
            if child_sbvalue and child_sbvalue.IsValid():
                return Value(child_sbvalue)
            raise IndexError("Index '%d' is out of range" % key)
        raise TypeError("No array item of type %s" % str(type(key)))

    def __iter__(self):
        return ValueIter(self.sbvalue)

    def __getattr__(self, name):
        child_sbvalue = self.sbvalue.GetChildMemberWithName (name)
        if child_sbvalue and child_sbvalue.IsValid():
            return Value(child_sbvalue)
        raise AttributeError("Attribute '%s' is not defined" % name)

    def __neg__(self):
        return -get_value(self)

    def __pos__(self):
        return +get_value(self)

    def __abs__(self):
        return abs(get_value(self))

    def __invert__(self):
        return ~get_value(self)

    def __complex__(self):
        return complex(get_value(self))

    def __int__(self):
        is_num, is_signed, is_float = is_numeric_type(self.sbvalue.GetType().GetCanonicalType().GetBasicType())
        if is_num and not is_signed: return self.sbvalue.GetValueAsUnsigned()
        return self.sbvalue.GetValueAsSigned()

    def __long__(self):
        return self.__int__()

    def __float__(self):
        is_num, is_signed, is_float = is_numeric_type(self.sbvalue.GetType().GetCanonicalType().GetBasicType())
        if is_num and is_float:
            return float(self.sbvalue.GetValue())
        else:
            return float(self.sbvalue.GetValueAsSigned())

    def __index__(self):
        return self.__int__()

    def __oct__(self):
        return '0%o' % self.sbvalue.GetValueAsUnsigned()

    def __hex__(self):
        return '0x%x' % self.sbvalue.GetValueAsUnsigned()

    def __len__(self):
        return self.sbvalue.GetNumChildren()

    # On-the-left ops
    def __add__(self, other):
        return get_value(self) + get_value(other)

    def __sub__(self, other):
        return get_value(self) - get_value(other)

    def __mul__(self, other):
        return get_value(self) * get_value(other)

    def __div__(self, other):
        return get_value(self) / get_value(other)

    def __floordiv__(self, other):
        return get_value(self) // get_value(other)

    def __truediv__(self, other):
        return get_value(self) / get_value(other)

    def __mod__(self, other):
        return get_value(self) % get_value(other)

    def __divmod__(self, other):
        return divmod(get_value(self), get_value(other))

    def __pow__(self, other):
        return get_value(self) ** get_value(other)

    def __lshift__(self, other):
        return get_value(self) << get_value(other)

    def __rshift__(self, other):
        return get_value(self) >> get_value(other)

    def __and__(self, other):
        return get_value(self) & get_value(other)

    def __xor__(self, other):
        return get_value(self) ^ get_value(other)

    def __or__(self, other):
        return get_value(self) | get_value(other)

    # On-the-right ops
    def __radd__(self, other):
        return get_value(other) + get_value(self)

    def __rsub__(self, other):
        return get_value(other) - get_value(self)

    def __rmul__(self, other):
        return get_value(other) * get_value(self)

    def __rdiv__(self, other):
        return get_value(other) / get_value(self)

    def __rfloordiv__(self, other):
        return get_value(other) // get_value(self)

    def __rtruediv__(self, other):
        return get_value(other) / get_value(self)

    def __rmod__(self, other):
        return get_value(other) % get_value(self)

    def __rdivmod__(self, other):
        return divmod(get_value(other), get_value(self))

    def __rpow__(self, other):
        return get_value(other) ** get_value(self)

    def __rlshift__(self, other):
        return get_value(other) << get_value(self)

    def __rrshift__(self, other):
        return get_value(other) >> get_value(self)

    def __rand__(self, other):
        return get_value(other) & get_value(self)

    def __rxor__(self, other):
        return get_value(other) ^ get_value(self)

    def __ror__(self, other):
        return get_value(other) | get_value(self)

    # In-place ops
    def __inplace(self, result):
        self.sbvalue.SetValueFromCString(str(result))
        return result

    def __iadd__(self, other):
        return self.__inplace(self.__add__(other))

    def __isub__(self, other):
        return self.__inplace(self.__sub__(other))

    def __imul__(self, other):
        return self.__inplace(self.__mul__(other))

    def __idiv__(self, other):
        return self.__inplace(self.__div__(other))

    def __itruediv__(self, other):
        return self.__inplace(self.__truediv__(other))

    def __ifloordiv__(self, other):
        return self.__inplace(self.__floordiv__(other))

    def __imod__(self, other):
        return self.__inplace(self.__mod__(other))

    def __ipow__(self, other):
        return self.__inplace(self.__pow__(other))

    def __ilshift__(self, other):
        return self.__inplace(self.__lshift__(other))

    def __irshift__(self, other):
        return self.__inplace(self.__rshift__(other))

    def __iand__(self, other):
        return self.__inplace(self.__and__(other))

    def __ixor__(self, other):
        return self.__inplace(self.__xor__(other))

    def __ior__(self, other):
        return self.__inplace(self.__or__(other))

    # Comparisons
    def __compare(self, other, op):
        if type(other) is int:
            return op(int(self), other)
        elif type(other) is float:
            return op(float(self), other)
        elif type(other) is str:
            return op(str(self), other)
        elif type(other) is Value:
            return op(get_value(self), get_value(other))
        raise TypeError("Unknown type %s, No comparison operation defined." % str(type(other)))

    def __lt__(self, other):
        return self.__compare(other, operator.lt)

    def __le__(self, other):
        return self.__compare(other, operator.le)

    def __gt__(self, other):
        return self.__compare(other, operator.gt)

    def __ge__(self, other):
        return self.__compare(other, operator.ge)

    def __eq__(self, other):
        return self.__compare(other, operator.eq)

    def __ne__(self, other):
        return self.__compare(other, operator.ne)

class ValueIter(object):
    def __init__(self,Value):
        self.index = 0
        self.sbvalue = Value
        if type(self.sbvalue) is Value:
            self.sbvalue = self.sbvalue.sbvalue
        self.length = self.sbvalue.GetNumChildren()

    def __iter__(self):
        return self

    def __next__(self):
        if self.index >= self.length:
            raise StopIteration()
        child_sbvalue = self.sbvalue.GetChildAtIndex(self.index)
        self.index += 1
        return Value(child_sbvalue)

    next = __next__ # PY2 compatibility.

# Converts a Value to an int, a float or a string
def get_value(v):
    if type(v) is Value:
        is_num, is_signed, is_float = is_numeric_type(v.sbvalue.GetType().GetCanonicalType().GetBasicType())
        if is_num:
            if is_float:
                return float(v.sbvalue.GetValue())
            elif is_signed:
                return v.sbvalue.GetValueAsSigned()
            else:
                return v.sbvalue.GetValueAsUnsigned()
        else:
            str_val = v.sbvalue.GetSummary()
            if str_val.startswith('"') and str_val.endswith('"') and len(str_val) > 1:
                str_val = str_val[1:-1]
            return str_val
    else:
        return v # passthrough

# given an lldb.SBBasicType it returns a tuple (is_numeric, is_signed, is_float)
def is_numeric_type(basic_type):
    return type_traits.get(basic_type, (False, False, False))
type_traits = {
    lldb.eBasicTypeInvalid: (False, False, False),
    lldb.eBasicTypeVoid: (False, False, False),
    lldb.eBasicTypeChar: (True, False, False),
    lldb.eBasicTypeSignedChar: (True, True, False),
    lldb.eBasicTypeUnsignedChar: (True, False, False),
    lldb.eBasicTypeWChar: (True, False, False),
    lldb.eBasicTypeSignedWChar: (True, True, False),
    lldb.eBasicTypeUnsignedWChar: (True, False, False),
    lldb.eBasicTypeChar16: (True, False, False),
    lldb.eBasicTypeChar32: (True, False, False),
    lldb.eBasicTypeShort: (True, True, False),
    lldb.eBasicTypeUnsignedShort: (True, False, False),
    lldb.eBasicTypeInt: (True, True, False),
    lldb.eBasicTypeUnsignedInt: (True, False, False),
    lldb.eBasicTypeLong: (True, True, False),
    lldb.eBasicTypeUnsignedLong: (True, False, False),
    lldb.eBasicTypeLongLong: (True, True, False),
    lldb.eBasicTypeUnsignedLongLong: (True, False, False),
    lldb.eBasicTypeInt128: (True, True, False),
    lldb.eBasicTypeUnsignedInt128: (True, False, False),
    lldb.eBasicTypeBool: (False, False, False),
    lldb.eBasicTypeHalf: (True, True, True),
    lldb.eBasicTypeFloat: (True, True, True),
    lldb.eBasicTypeDouble: (True, True, True),
    lldb.eBasicTypeLongDouble: (True, True, True),
    lldb.eBasicTypeFloatComplex: (True, True, False),
    lldb.eBasicTypeDoubleComplex: (True, True, False),
    lldb.eBasicTypeLongDoubleComplex: (True, True, False),
    lldb.eBasicTypeObjCID: (False, False, False),
    lldb.eBasicTypeObjCClass: (False, False, False),
    lldb.eBasicTypeObjCSel: (False, False, False),
    lldb.eBasicTypeNullPtr: (False, False, False),
}

# Replaces Python keywords with either `locals()["<ident>"]` or `.__getattr__("<ident>")`.
# Replaces qualified identifiers (e.g. `foo::bar::baz`) with `locals()["<ident>"]`.
def preprocess(expr):
    return preprocess_regex.sub(replacer, expr)

def preprocess_vars(expr):
    return preprocess_vars_regex.sub(replacer, expr)

pystrings = '|'.join([
    r'(?:"(?:\\"|\\\\|[^"])*")',
    r"(?:'(?:\\'|\\\\|[^'])*')",
    r'(?:r"[^"]*")',
    r"(?:r'[^']*')",
])
keywords = '|'.join(keyword.kwlist)
ident = r'\w+'
qualified_ident = r'(?: \w+ ::)+ \w+'
preprocess_regex = re.compile(r'(\.)? \b ({keywords} | {qualified_ident}) \b | {pystrings}'.format(**locals()), re.X)

maybe_qualified_ident = r'(?: \w+ ::)* \w+'
preprocess_vars_regex = re.compile(r'(\.)? \$ ({maybe_qualified_ident}) \b | {pystrings}'.format(**locals()), re.X)

def replacer(match):
    prefix = match.group(1)
    ident = match.group(2)
    if ident is not None:
        if prefix is None:
            return 'locals()["%s"]' % ident
        elif prefix == '.':
            return '.__getattr__("%s")' % ident
        else:
            assert False
    else: # a string - return unchanged
        return match.group(0)

def test_preprocess():
    expr = """
        class = from.global.finally
        local::bar::__BAZ()
        local_string()
        '''continue.exec = pass.print; yield.with = 3'''
        "continue.exec = pass.print; yield.with = 3"
    """
    expected = """
        locals()["class"] = locals()["from"].__getattr__("global").__getattr__("finally")
        locals()["local::bar::__BAZ"]()
        local_string()
        '''continue.exec = pass.print; yield.with = 3'''
        "continue.exec = pass.print; yield.with = 3"
    """
    prepr = preprocess(expr)
    if prepr != expected:
        print(expected)
        print(prepr)
    assert prepr == expected

def test_preprocess_vars():
    expr = """
        for x in $foo: print x
        $xxx.$yyy.$zzz
        $xxx::yyy::zzz
        "$xxx::yyy::zzz"
    """
    expected = """
        for x in locals()["foo"]: print x
        locals()["xxx"].__getattr__("yyy").__getattr__("zzz")
        locals()["xxx::yyy::zzz"]
        "$xxx::yyy::zzz"
    """
    prepr = preprocess_vars(expr)
    if prepr != expected:
        print(expected)
        print(prepr)
    assert prepr == expected

def run_tests():
    test_preprocess()
    test_preprocess_vars()
