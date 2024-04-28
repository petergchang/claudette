# AUTOGENERATED! DO NOT EDIT! File to edit: ../00_core.ipynb.

# %% auto 0
__all__ = ['models', 'empty', 'g', 'tags', 'mk_msg', 'find_block', 'contents', 'mk_msgs', 'usage', 'Client', 'get_schema',
           'mk_ns', 'call_func', 'mk_toolres', 'Chat', 'hl_md', 'to_xml', 'xt', 'json_to_xml']

# %% ../00_core.ipynb 6
import tokenize, ast, inspect, inspect, typing
import xml.etree.ElementTree as ET, json
from collections import abc

from anthropic import Anthropic
from anthropic.types import Usage, TextBlock, Message
from anthropic.types.beta.tools import ToolsBetaMessage, tool_use_block
from inspect import Parameter
from io import BytesIO
try: from IPython.display import Markdown,HTML
except: Markdown,HTML=None,None

from fastcore.docments import docments
from fastcore.utils import *

# %% ../00_core.ipynb 7
models = 'claude-3-opus-20240229','claude-3-sonnet-20240229','claude-3-haiku-20240307'

# %% ../00_core.ipynb 9
empty = Parameter.empty

# %% ../00_core.ipynb 17
def mk_msg(content, role='user', **kw):
    "Helper to create a `dict` appropriate for a Claude message."
    if hasattr(content, 'content'): content,role = content.content,content.role
    if isinstance(content, abc.Mapping): content=content['content']
    return dict(role=role, content=content, **kw)

# %% ../00_core.ipynb 21
def find_block(r, blk_type=TextBlock):
    "Find the first block of type `blk_type` in `r.content`."
    return first(o for o in r.content if isinstance(o,blk_type))

# %% ../00_core.ipynb 24
def contents(r):
    "Helper to get the contents from Claude response `r`."
    blk = find_block(r)
    if not blk: blk = r.content[0]
    return blk.text.strip() if hasattr(blk,'text') else blk

# %% ../00_core.ipynb 27
def mk_msgs(msgs, **kw):
    "Helper to set 'assistant' role on alternate messages."
    if isinstance(msgs,str): msgs=[msgs]
    return [mk_msg(o, ('user','assistant')[i%2], **kw) for i,o in enumerate(msgs)]

# %% ../00_core.ipynb 37
def usage(inp=0, out=0):
    "Slightly more concise version of `Usage`."
    return Usage(input_tokens=inp, output_tokens=out)

# %% ../00_core.ipynb 40
@patch(as_prop=True)
def total(self:Usage): return self.input_tokens+self.output_tokens

# %% ../00_core.ipynb 43
@patch
def __repr__(self:Usage): return f'In: {self.input_tokens}; Out: {self.output_tokens}; Total: {self.total}'

# %% ../00_core.ipynb 46
@patch
def __add__(self:Usage, b):
    return usage(self.input_tokens+b.input_tokens, self.output_tokens+b.output_tokens)

# %% ../00_core.ipynb 50
class Client:
    def __init__(self, model, cli=None):
        "Basic Anthropic messages client."
        self.model,self.use = model,Usage(input_tokens=0,output_tokens=0)
        self.c = (cli or Anthropic())

# %% ../00_core.ipynb 53
@patch
def _r(self:Client, r:ToolsBetaMessage):
    "Store the result of the message and accrue total usage."
    self.result = r
    self.use += r.usage
    return r

# %% ../00_core.ipynb 56
@patch
def __call__(self:Client, msgs, sp='', temp=0, maxtok=4096, stop=None, **kw):
    "Make a call to Claude without streaming."
    r = self.c.beta.tools.messages.create(
        model=self.model, messages=mk_msgs(msgs), max_tokens=maxtok, system=sp, temperature=temp, stop_sequences=stop, **kw)
    return self._r(r)

# %% ../00_core.ipynb 60
@patch
def stream(self:Client, msgs, sp='', temp=0, maxtok=4096, stop=None, **kw):
    "Make a call to Claude, streaming the result."
    with self.c.messages.stream(model=self.model, messages=mk_msgs(msgs), max_tokens=maxtok,
                                system=sp, temperature=temp, stop_sequences=stop, **kw) as s:
        yield from s.text_stream
        return self._r(s.get_final_message())

# %% ../00_core.ipynb 72
def _types(t:type)->tuple[str,Optional[str]]:
    "Tuple of json schema type name and (if appropriate) array item name."
    tmap = {int:"integer", float:"number", str:"string", bool:"boolean", list:"array", dict:"object"}
    if getattr(t, '__origin__', None) in  (list,tuple): return "array", tmap.get(t.__args__[0], "object")
    else: return tmap.get(t, "object"), None

# %% ../00_core.ipynb 75
def _param(name, info):
    "json schema parameter given `name` and `info` from docments full dict."
    paramt,itemt = _types(info.anno)
    pschema = dict(type=paramt, description=info.docment)
    if itemt: pschema["items"] = {"type": itemt}
    if info.default is not empty: pschema["default"] = info.default
    return pschema

# %% ../00_core.ipynb 78
def get_schema(f:callable)->dict:
    "Convert function `f` into a JSON schema `dict` for tool use."
    d = docments(f, full=True)
    ret = d.pop('return')
    paramd = {
        'type': "object",
        'properties': {n:_param(n,o) for n,o in d.items()},
        'required': [n for n,o in d.items() if o.default is empty]
    }
    desc = f.__doc__
    if ret.anno is not empty: desc += f'\n\nReturns:\n- type: {_types(ret.anno)[0]}'
    if ret.docment: desc += f'\n- description: {ret.docment}'
    return dict(name=f.__name__, description=desc, input_schema=paramd)

# %% ../00_core.ipynb 89
def mk_ns(*funcs:list[callable]) -> dict[str,callable]:
    "Create a `dict` of name to function in `funcs`, to use as a namespace"
    return {f.__name__:f for f in funcs}

# %% ../00_core.ipynb 91
def call_func(tr, ns=None):
    "Call the function in the tool response `tr`, using namespace `ns`."
    if ns is None: ns=globals()
    if not isinstance(ns, abc.Mapping): ns = mk_ns(*ns)
    fc = find_block(r, tool_use_block.ToolUseBlock)
    return ns[fc.name](**fc.input)

# %% ../00_core.ipynb 94
def mk_toolres(r, res=None, ns=None):
    "Create a `tool_result` message from response `r`."
    if not hasattr(r, 'content'): return r
    tool = first(o for o in r.content if isinstance(o,tool_use_block.ToolUseBlock))
    if not tool: return r
    if res is None: res = call_func(r, ns)
    tr = dict(type="tool_result", tool_use_id=tool.id, content=str(res))
    return mk_msg([tr])

# %% ../00_core.ipynb 101
class Chat:
    def __init__(self, model=None, cli=None, sp='', tools=None):
        "Anthropic chat client."
        assert model or cli
        self.c = (cli or Client(model))
        self.h,self.sp,self.tools = [],sp,tools

# %% ../00_core.ipynb 114
def hl_md(s, lang='xml'):
    "Syntax highlight `s` using `lang`."
    if Markdown: return Markdown(f'```{lang}\n{s}\n```')
    print(s)

# %% ../00_core.ipynb 115
def to_xml(node, hl=False):
    "Convert `node` to an XML string."
    def mk_el(tag, cs, attrs):
        el = ET.Element(tag, attrib=attrs)
        if isinstance(cs, list): el.extend([mk_el(*o) for o in cs])
        elif cs is not None: el.text = str(cs)
        return el

    root = mk_el(*node)
    ET.indent(root)
    res = ET.tostring(root, encoding='unicode')
    return hl_md(res) if hl else res

# %% ../00_core.ipynb 116
def xt(tag, c=None, **kw):
    "Helper to create appropriate data structure for `to_xml`."
    kw = {k.lstrip('_'):str(v) for k,v in kw.items()}
    return tag,c,kw

# %% ../00_core.ipynb 117
g = globals()
tags = 'div','img','h1','h2','h3','h4','h5','p','hr','span','html'
for o in tags: g[o] = partial(xt, o)

# %% ../00_core.ipynb 120
def json_to_xml(d:dict, rnm:str)->str:
    "Convert `d` to XML with root name `rnm`."
    root = ET.Element(rnm)
    def build_xml(data, parent):
        if isinstance(data, dict):
            for key, value in data.items(): build_xml(value, ET.SubElement(parent, key))
        elif isinstance(data, list):
            for item in data: build_xml(item, ET.SubElement(parent, 'item'))
        else: parent.text = str(data)
    build_xml(d, root)
    ET.indent(root)
    return ET.tostring(root, encoding='unicode')
