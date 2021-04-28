from abc import abstractmethod
from typing import Callable, Dict, Iterator, List, Optional, Set, Tuple, Union, cast

from jsonschema import RefResolver
from unidecode import unidecode

from jsonschema_gentypes import configuration, jsonschema

# Raise issues here.
ISSUE_URL = "https://github.com/camptcamp/jsonschema-gentypes"


class Type:
    _comments: Optional[List[str]] = None

    def name(self) -> str:
        """
        Return what we need to use the type
        """
        raise NotImplementedError

    def imports(self) -> List[Tuple[str, str]]:  # pylint: disable=no-self-use
        """
        Return the needed imports
        """
        return []

    def definition(self) -> List[str]:  # pylint: disable=no-self-use
        """
        Return the type declaration
        """
        return []

    def depends_on(self) -> List["Type"]:  # pylint: disable=no-self-use
        """
        Return the needed sub types
        """
        return []

    def comments(self) -> List[str]:
        """
        Additional comments shared by the type
        """
        if self._comments is None:
            self._comments = []
        return self._comments

    def set_comments(self, comments: List[str]) -> None:
        self._comments = comments


class NamedType(Type):
    def __init__(self, name: str) -> None:
        self._name = name

    def postfix_name(self, postfix: str) -> None:
        """
        Set a new name (Not available every time)
        """
        self._name += postfix

    def set_name(self, name: str) -> None:
        """
        Set a new name (Not available every time)
        """
        self._name = name

    def unescape_name(self) -> str:
        return self._name

    def name(self) -> str:
        return f'"{self._name}"'


class LiteralType(Type):
    def __init__(self, const: Union[int, float, bool, str, None]) -> None:
        self.const = const

    def name(self) -> str:
        if isinstance(self.const, str):
            return f'Literal["{self.const}"]'
        else:
            return f"Literal[{self.const}]"

    def imports(self) -> List[Tuple[str, str]]:
        return [("typing", "Literal")]


class BuiltinType(Type):
    def __init__(self, name: str) -> None:
        self._name = name

    def name(self) -> str:
        return self._name


class NativeType(Type):
    def __init__(self, name: str, package: str = "typing") -> None:
        self.package = package
        self._name = name

    def name(self) -> str:
        return self._name

    def imports(self) -> List[Tuple[str, str]]:
        return [(self.package, self._name)]


class CombinedType(Type):
    def __init__(self, base: Type, sub_types: List[Type]) -> None:
        self.base = base
        self.sub_types = sub_types
        self.name()

    def name(self) -> str:
        assert isinstance(self.base, Type)
        return f"{self.base.name()}[{', '.join([sub_type.name() for sub_type in self.sub_types])}]"

    def depends_on(self) -> List[Type]:
        return [self.base] + self.sub_types


class TypeAlias(NamedType):
    def __init__(self, name: str, sub_type: Type, descriptions: Optional[List[str]] = None):
        super().__init__(name)
        self.sub_type = sub_type
        self.descriptions = [] if descriptions is None else descriptions

    def depends_on(self) -> List[Type]:
        return [self.sub_type]

    def definition(self) -> List[str]:
        result = ["", ""]
        result += ["# " + d for d in self.descriptions]
        result.append(f"{self._name} = {self.sub_type.name()}")
        return result


class TypeEnum(NamedType):
    def __init__(
        self,
        name: str,
        values: List[Union[int, float, bool, str, None]],
        descriptions: Optional[List[str]] = None,
    ):
        super().__init__(name)
        assert len(values) > 0
        self.values = values
        self.descriptions = [] if descriptions is None else descriptions

    def imports(self) -> List[Tuple[str, str]]:
        return [("enum", "Enum")]

    def definition(self) -> List[str]:
        result = ["", ""]
        result += ["# " + d for d in self.descriptions]
        result.append(f"class {self._name}(Enum):")
        for value in self.values:
            if isinstance(value, str):
                result.append(f'    {get_name({"title": value}, upper=True)} = "{value}"')
            else:
                result.append(f'    {get_name({"title": str(value)}, upper=True)} = {value}')
        return result


class TypedDictType(NamedType):
    def __init__(
        self,
        name: str,
        struct: Dict[str, Type],
        descriptions: List[str],
    ):
        super().__init__(name)
        self.descriptions = descriptions
        self.struct = struct

    def depends_on(self) -> List[Type]:
        result: List[Type] = [NativeType("TypedDict")]
        result += self.struct.values()
        return result

    def definition(self) -> List[str]:
        """
        Get the definition based on a dict
        """
        result = ["", ""]
        result += ["# " + d for d in self.descriptions]
        result.append(f"{self._name} = TypedDict('{self._name}', " + "{")
        for property_, type_obj in self.struct.items():
            for comment in type_obj.comments():
                result.append(f"    # {comment}")
            result.append(f"    '{property_}': {type_obj.name()},")
        result.append("}, total=False)")
        return result


def char_range(char1: str, char2: str) -> Iterator[str]:
    """Generates the characters from `char1` to `char2`, inclusive."""
    for char in range(ord(char1), ord(char2) + 1):
        yield chr(char)


def get_name(
    schema: Optional[jsonschema.JSONSchemaItem],
    proposed_name: Optional[str] = None,
    upper: bool = False,
) -> str:
    # Get the base name
    has_title = isinstance(schema, dict) and "title" in schema
    name = schema["title"] if has_title else proposed_name  # type: ignore
    assert name is not None
    # Unaccent, ...
    name = unidecode(name)
    # Remove unauthorised char
    authorised_char = list(char_range("a", "z")) + list(char_range("A", "Z")) + list(char_range("0", "9"))
    name = "".join([(c if c in authorised_char else " ") for c in name])
    # No number at first position
    if name[0] in list(char_range("0", "9")):
        name = f"num {name}"
    # No python keyword
    if name.lower() in [
        "and",
        "as",
        "assert",
        "break",
        "class",
        "continue",
        "def",
        "del",
        "elif",
        "else",
        "except",
        "false",
        "finally",
        "for",
        "from",
        "global",
        "if",
        "import",
        "in",
        "is",
        "lambda",
        "none",
        "nonlocal",
        "not",
        "or",
        "pass",
        "raise",
        "return",
        "true",
        "try",
        "while",
        "with",
        "yield",
    ]:
        name = f"{name} name"
    prefix = "" if has_title else "_"
    if upper:
        # Upper case
        name = name.upper()
        # Remove spaces
        return prefix + "".join(["_" if char.isspace() else char for char in name])
    else:
        # Title case
        name = name.title()
        # Remove spaces
        return prefix + "".join([char for char in name if not char.isspace()])


def get_description(schema: jsonschema.JSONSchemaItem) -> List[str]:
    result: List[str] = []
    for key in ("title", "description"):
        if key in schema:
            if result:
                result.append("")
            result.append(schema[key])  # type: ignore
    first = True
    for key, value in schema.items():
        if (
            key
            not in (
                "title",
                "description",
                "$ref",
                "$schema",
                "$id",
                "const",
                "type",
                "items",
                "additionalProperties",
            )
            and not isinstance(value, list)
            and not isinstance(value, dict)
        ):
            if first:
                if result:
                    result.append("")
                first = False
            result.append(f"{key}: {value}")

    return result


class API:
    """Base class for JSON schema types API."""

    def __init__(
        self,
        resolver: RefResolver,
        additional_properties: configuration.AdditionalProperties = configuration.AdditionalProperties.ONLY_EXPLICIT,
    ) -> None:
        """Initialize with a resolver."""
        self.resolver = resolver
        self.additional_properties = additional_properties
        # types by reference
        self.ref_type: Dict[str, Type] = {}

    def get_type_handler(self, schema_type: str) -> Callable[[jsonschema.JSONSchemaItem, str], Type]:
        """Get a handler from this schema draft version."""
        if schema_type.startswith("_"):
            raise AttributeError("No way friend")
        handler = cast(Callable[[jsonschema.JSONSchemaItem, str], Type], getattr(self, schema_type, None))
        if handler is None:
            raise NotImplementedError(
                f"Type `{schema_type}` is not supported. If you think that this is an error, "
                f"say something at {ISSUE_URL}"
            )
        return handler

    def get_type(
        self, schema: jsonschema.JSONSchema, proposed_name: str = "Base", auto_alias: bool = True
    ) -> Type:
        """Get a :class:`.Type` for a JSON schema."""
        if schema is True:
            return NativeType("Any")
        if schema is False:
            return BuiltinType("None")
        assert not isinstance(schema, bool)

        the_type = self._get_type_internal(schema, proposed_name)
        assert the_type is not None
        additional_description = the_type.comments()
        description = get_description(schema)
        if description and additional_description:
            description.append("")
        description += additional_description
        if not isinstance(the_type, NamedType) and description:
            if auto_alias:
                return TypeAlias(get_name(schema, proposed_name), the_type, description)
            else:
                the_type.set_comments(description)

        return the_type

    def _resolve_ref(self, schema: jsonschema.JSONSchemaItem) -> jsonschema.JSONSchemaItem:
        if "$ref" in schema:
            with self.resolver.resolving(schema["$ref"]) as resolved:
                schema.update(resolved)
        return schema

    def _get_type_internal(self, schema: jsonschema.JSONSchemaItem, proposed_name: str) -> Type:
        """Get a :class:`.Type` for a JSON schema."""

        scope = schema.get("$id", "")
        if scope:
            self.resolver.push_scope(scope)
        proposed_name = schema.get("title", proposed_name)

        if "if" in schema:
            base_schema: jsonschema.JSONSchemaItem = {}
            base_schema.update(schema)
            for key in ("if", "then", "else", "title", "description"):
                if key in base_schema:
                    del base_schema[key]  # type: ignore
            then_schema: jsonschema.JSONSchemaItem = {}
            then_schema.update(base_schema)
            then_schema.update(self._resolve_ref(cast(jsonschema.JSONSchemaItem, schema.get("then", {}))))
            if "properties" not in then_schema:
                then_schema["properties"] = {}
            then_propoerties = then_schema["properties"]
            assert then_propoerties
            if_properties = self._resolve_ref(cast(jsonschema.JSONSchemaItem, schema.get("if", {}))).get(
                "properties", {}
            )
            assert if_properties
            then_propoerties.update(if_properties)
            else_schema: jsonschema.JSONSchemaItem = {}
            else_schema.update(base_schema)
            else_schema.update(self._resolve_ref(cast(jsonschema.JSONSchemaItem, schema.get("else", {}))))

            return CombinedType(
                NativeType("Union"),
                [
                    self.get_type(then_schema, proposed_name + " then"),
                    self.get_type(else_schema, proposed_name + " else"),
                ],
            )

        if "$ref" in schema:
            return self.ref(schema, proposed_name)

        if "const" in schema:
            return self.const(schema, proposed_name)

        # 6.1.1. type
        # The value of this keyword MUST be either a string or an array. If it
        # is an array, elements of the array MUST be strings and MUST be
        # unique.
        #
        # String values MUST be one of the six primitive types ("null",
        # "boolean", "object", "array", "number", or "string"), or "integer"
        # which matches any number with a zero fractional part.
        #
        # An instance validates if and only if the instance is in any of the
        # sets listed for this keyword.
        schema_type = schema.get("type")
        if isinstance(schema_type, list):
            inner_types = []
            proposed_name = schema.get("title", proposed_name)
            schema_copy = cast(jsonschema.JSONSchemaItem, dict(schema))
            if "title" in schema_copy:
                del schema_copy["title"]
            for primitive_type in schema_type:
                inner_types.append(
                    self._get_type(
                        schema_copy, cast(str, primitive_type), f"{proposed_name} {primitive_type}"
                    )
                )
            return CombinedType(NativeType("Union"), inner_types)
        elif schema_type is None:
            if "allOf" in schema:
                return self.all_of(
                    schema, cast(List[jsonschema.JSONSchemaItem], schema["allOf"]), proposed_name
                )
            elif "anyOf" in schema:
                return self.any_of(
                    schema, cast(List[jsonschema.JSONSchemaItem], schema["anyOf"]), proposed_name
                )
            elif "oneOf" in schema:
                return self.any_of(
                    schema, cast(List[jsonschema.JSONSchemaItem], schema["oneOf"]), proposed_name
                )
            elif "enum" in schema:
                return self.enum(schema, proposed_name)
            elif "default" in schema:
                return self.default(schema, proposed_name)
        if scope:
            self.resolver.pop_scope()

        if schema_type is None:
            type_ = BuiltinType("None")
            type_.set_comments(["WARNING: we get an scheam without any type"])
            return type_
        assert isinstance(schema_type, str), (
            f"Expected to find a supported schema type, got {schema_type}" f"\nDuring parsing of {schema}"
        )

        return self._get_type(schema, schema_type, proposed_name)

    def _get_type(self, schema: jsonschema.JSONSchemaItem, schema_type: str, proposed_name: str) -> Type:

        proposed_name = schema.get("title", proposed_name)

        # Enums get special treatment, as they should be one of the literal values.
        # Note: If a "type" field indicates types that are incompatible with some of
        # the enumeration values (which is allowed by jsonschema), the "type" will _not_
        # be respected. This should be considered a malformed schema anyway, so this
        # will not be fixed.
        if "enum" in schema:
            handler = self.get_type_handler("enum")
            return handler(schema, proposed_name)

        handler = self.get_type_handler(schema_type)
        if handler is not None:
            return handler(schema, proposed_name)

        type_ = BuiltinType("None")
        type_.set_comments(
            [
                f"WARNING: No handler for `{schema_type}`; please raise an issue",
                f"at {ISSUE_URL} if you believe this to be in error",
            ]
        )
        return type_

    @abstractmethod
    def ref(self, schema: jsonschema.JSONSchemaItem, proposed_name: str) -> Type:
        pass

    @abstractmethod
    def all_of(
        self,
        schema: jsonschema.JSONSchemaItem,
        subschema: List[jsonschema.JSONSchemaItem],
        proposed_name: str,
    ) -> Type:
        pass

    @abstractmethod
    def any_of(
        self,
        schema: jsonschema.JSONSchemaItem,
        subschema: List[jsonschema.JSONSchemaItem],
        proposed_name: str,
    ) -> Type:
        pass

    @abstractmethod
    def const(self, schema: jsonschema.JSONSchemaItem, proposed_name: str) -> Type:
        pass

    @abstractmethod
    def enum(self, schema: jsonschema.JSONSchemaItem, proposed_name: str) -> Type:
        pass

    @abstractmethod
    def default(self, schema: jsonschema.JSONSchemaItem, proposed_name: str) -> Type:
        pass


class APIv4(API):
    """JSON Schema draft 4."""

    def const(self, schema: jsonschema.JSONSchemaItem, proposed_name: str) -> Type:
        """Generate a ``Literal`` for a const value."""
        const_: Union[int, float, str, bool, None] = schema["const"]
        return LiteralType(const_)

    def enum(self, schema: jsonschema.JSONSchemaItem, proposed_name: str) -> Type:
        """Generate an enum."""
        return TypeEnum(
            get_name(schema, proposed_name),
            cast(List[Union[int, float, bool, str, None]], schema["enum"]),
            get_description(schema),
        )

    def boolean(  # pylint: disable=no-self-use
        self, schema: jsonschema.JSONSchemaItem, proposed_name: str
    ) -> Type:
        """Generate a ``bool`` annotation for a boolean object."""
        del schema, proposed_name
        return BuiltinType("bool")

    def object(self, schema: jsonschema.JSONSchemaItem, proposed_name: str) -> Type:
        """Generate an annotation for an object, usually a TypedDict."""

        std_dict = None
        name = get_name(schema, proposed_name)
        additional_properties = cast(jsonschema.JSONSchema, schema.get("additionalProperties"))
        if (
            additional_properties is True
            and self.additional_properties == configuration.AdditionalProperties.ALWAYS
        ):
            std_dict = CombinedType(NativeType("Dict"), [BuiltinType("str"), NativeType("Any")])
        elif isinstance(additional_properties, dict):
            sub_type = self.get_type(additional_properties, f"{proposed_name} additionalProperties")
            std_dict = CombinedType(NativeType("Dict"), [BuiltinType("str"), sub_type])
        properties = cast(Dict[str, jsonschema.JSONSchemaItem], schema.get("properties"))
        proposed_name = schema.get("title", proposed_name)
        if properties:
            required = set(schema.get("required", []))

            def add_required(type_: Type, prop: str, required: Set[str]) -> Type:
                if prop in required:
                    comments = type_.comments()
                    if comments:
                        comments.append("")
                    comments.append("required")
                return type_

            struct = {
                prop: add_required(
                    self.get_type(subschema, proposed_name + " " + prop, auto_alias=False), prop, required
                )
                for prop, subschema in properties.items()
            }

            # With Python 3.10 this can be better.
            # See: https://www.python.org/dev/peps/pep-0655/
            type_: Type = TypedDictType(
                name if std_dict is None else name + "Typed",
                struct,
                get_description(schema) if std_dict is None else [],
            )

            comments = [
                "WARNING: The required are not correctly taken in account,",
                "See: https://www.python.org/dev/peps/pep-0655/",
            ]

            if std_dict is not None:
                type_ = CombinedType(NativeType("Union"), [std_dict, type_])
                comments += [
                    "",
                    "WARNING: the Normally the types should be mised each other instead of Union.",
                    "See: https://github.com/python/mypy/issues/6131",
                ]

            type_.set_comments(comments)
            return type_
        if std_dict is not None:
            return std_dict
        return CombinedType(NativeType("Dict"), [BuiltinType("str"), NativeType("Any")])

    def array(self, schema: jsonschema.JSONSchemaItem, proposed_name: str) -> Type:
        """Generate a ``List[]`` annotation with the allowed types."""
        items = schema.get("items")
        if items is True:  # type: ignore
            return CombinedType(NativeType("List"), [NativeType("Any")])
        elif items is False:  # type: ignore
            raise NotImplementedError('"items": false is not supported')
        elif isinstance(items, list):
            inner_types = [self.get_type(cast(jsonschema.JSONSchemaItem, item)) for item in items]
            type_: Type = CombinedType(NativeType("Tuple"), inner_types)
            if {schema.get("minItems"), schema.get("maxItems")} - {None, len(items)}:
                type_.set_comments(
                    [
                        "WARNING: 'items': If list, must have minItems == maxItems.",
                        "See: https://json-schema.org/understanding-json-schema/"
                        "reference/array.html#tuple-validation",
                    ]
                )
                return type_
            return type_
        elif items is not None:
            return CombinedType(
                NativeType("List"),
                [self.get_type(cast(jsonschema.JSONSchemaItem, items), proposed_name + " item")],
            )
        else:
            type_ = BuiltinType("None")
            type_.set_comments(["WARNING: we get an array without any items"])
            return type_

    def all_of(
        self,
        schema: jsonschema.JSONSchemaItem,
        subschema: List[jsonschema.JSONSchemaItem],
        proposed_name: str,
    ) -> Type:
        """
        Generate a ``Union`` annotation with the allowed types.

        Unfortunately PEP 544 currently does not support an Intersection type;
        see `this issue <https://github.com/python/typing/issues/213>`_ for
        some context.
        """
        inner_types = list(
            filter(
                lambda o: o is not None,
                [
                    self.get_type(subs, f"{proposed_name} allof{index}")
                    for index, subs in enumerate(subschema)
                ],
            )
        )

        type_ = CombinedType(NativeType("Union"), inner_types)
        type_.set_comments(
            [
                "WARNING: PEP 544 does not support an Intersection type,",
                "so `allOf` is interpreted as a `Union` for now.",
                "See: https://github.com/python/typing/issues/213",
            ]
        )
        return type_

    def any_of(
        self,
        schema: jsonschema.JSONSchemaItem,
        subschema: List[jsonschema.JSONSchemaItem],
        proposed_name: str,
    ) -> Type:
        """Generate a ``Union`` annotation with the allowed types."""
        inner_types = list(
            filter(
                lambda o: o is not None,
                [
                    self.get_type(subs, f"{proposed_name} anyof{index}")
                    for index, subs in enumerate(subschema)
                ],
            )
        )
        return CombinedType(NativeType("Union"), inner_types)

    def ref(self, schema: jsonschema.JSONSchemaItem, proposed_name: str) -> Type:
        """Handle a `$ref`."""
        ref = schema["$ref"]
        schema = cast(jsonschema.JSONSchemaItem, dict(schema))
        del schema["$ref"]
        if ref == "#":  # Self ref.
            # Per @ilevkivskyi:
            #
            # > You should never use ForwardRef manually
            # > Also it is deprecated and will be removed soon
            # > Support for recursive types is limited to proper classes
            # > currently
            #
            # forward_ref = ForwardRef(UnboundType(self.outer_name))
            # self.forward_refs.append(forward_ref)
            # return forward_ref

            type_ = self.object({}, proposed_name + " object")
            type_.set_comments(
                [
                    "WARNING: Forward references may not be supported.",
                    "See: https://github.com/python/mypy/issues/731",
                ]
            )
            return type_

        if ref in self.ref_type:
            return self.ref_type[ref]

        resolve = getattr(self.resolver, "resolve", None)
        if resolve is None:
            with self.resolver.resolving(ref) as resolved:
                schema.update(resolved)
                type_ = self.get_type(schema)
        else:
            scope, resolved = self.resolver.resolve(ref)
            self.resolver.push_scope(scope)
            try:
                schema.update(resolved)
                type_ = self.get_type(schema, proposed_name)
            finally:
                self.resolver.pop_scope()

        if ref:
            self.ref_type[ref] = type_
        return type_

    def string(  # pylint: disable=no-self-use
        self, schema: jsonschema.JSONSchemaItem, proposed_name: str
    ) -> Type:
        """Generate a ``str`` annotation."""
        del schema, proposed_name
        return BuiltinType("str")

    def number(  # pylint: disable=no-self-use
        self, schema: jsonschema.JSONSchemaItem, proposed_name: str
    ) -> Type:
        """Generate a ``Union[int, float]`` annotation."""
        del schema, proposed_name
        return CombinedType(NativeType("Union"), [BuiltinType("int"), BuiltinType("float")])

    def integer(  # pylint: disable=no-self-use
        self, schema: jsonschema.JSONSchemaItem, proposed_name: str
    ) -> Type:
        """Generate an ``int`` annotation."""
        del schema, proposed_name
        return BuiltinType("int")

    def null(  # pylint: disable=no-self-use
        self, schema: jsonschema.JSONSchemaItem, proposed_name: str
    ) -> Type:
        """Generate an ``None`` annotation."""
        del schema, proposed_name
        return BuiltinType("None")

    def default(self, schema: jsonschema.JSONSchemaItem, proposed_name: str) -> Type:
        """
        The ``default`` keyword is not supported.

        But see: `https://github.com/python/mypy/issues/6131`_.
        """
        comments = [
            "WARNING: `default` keyword not supported.",
            "See: https://github.com/python/mypy/issues/6131",
        ]
        type_ = "Any"
        for test_type, type_name in [
            (str, "str"),
            (int, "int"),
            (float, "float"),
            (bool, "bool"),
        ]:
            if isinstance(schema["default"], test_type):
                type_ = type_name
        the_type = BuiltinType(type_)
        the_type.set_comments(comments)
        return the_type


class APIv6(APIv4):
    """JSON Schema draft 6."""


class APIv7(APIv6):
    """JSON Schema draft 7."""
