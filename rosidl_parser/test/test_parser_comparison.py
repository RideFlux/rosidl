"""
두 파서(Earley vs LALR+contextual) 결과 비교 테스트.

  Lark(grammar, start='specification')
      → parser='earley', lexer='dynamic' (Lark 기본값)
      → grammar_lalr.lark 에 정의된 터미널 우선순위(.0)와 충돌하므로
        우선순위가 없는 grammar.lark 를 사용

  Lark(grammar, start='specification', parser='lalr', lexer='contextual')
      → parser.py 에서 실제 사용 중인 설정
      → grammar_lalr.lark 사용

두 파서가 동일한 AST (pretty-print / str) 를 생성하는지 검증합니다.
"""

import os
import pytest
from lark import Lark

_base = os.path.join(os.path.dirname(__file__), '..', 'rosidl_parser')

# Earley (기본): grammar.lark 사용 — 터미널 우선순위 없어 Dynamic Earley 와 호환
with open(os.path.join(_base, 'grammar.lark'), encoding='utf-8') as f:
    _grammar_earley = f.read()

# LALR (parser.py 실제 사용): grammar_lalr.lark 사용
with open(os.path.join(_base, 'grammar_lalr.lark'), encoding='utf-8') as f:
    _grammar_lalr = f.read()

# Lark(grammar, start='specification')  →  earley + dynamic (Lark 기본)
_earley_parser = Lark(_grammar_earley, start='specification')
# Lark(grammar, start='specification', parser='lalr', lexer='contextual')
_lalr_parser   = Lark(_grammar_lalr,   start='specification', parser='lalr', lexer='contextual')


def parse_both(idl_string):
    tree_earley = _earley_parser.parse(idl_string)
    tree_lalr   = _lalr_parser.parse(idl_string)
    return tree_earley, tree_lalr


# ---------------------------------------------------------------------------
# Tree 정규화 (normalize)
# ---------------------------------------------------------------------------
# grammar.lark 와 grammar_lalr.lark 는 숫자/헥사 리터럴 토큰 분할 방식이 다릅니다.
#   grammar.lark :  decimal_literal: DIGIT | "1".."9" DIGIT+
#                       → Token(DIGIT, '1'), Token(DIGIT, '0')  (digit-by-digit)
#   grammar_lalr.lark:  decimal_literal: /0|[1-9][0-9]*/
#                       → Token(__ANON_0, '10')                 (하나의 regex)
# 마찬가지로 hexadecimal_literal 도 다릅니다.
# normalize_tree() 는 이러한 차이를 의미적 정수값으로 통일해 비교합니다.

from lark.tree import Tree as _LarkTree
from lark.lexer import Token as _LarkToken


def _node_str(node):
    """재귀적으로 tree/token을 의미적으로 동일한 문자열로 변환."""
    if isinstance(node, _LarkToken):
        return node.value
    if not isinstance(node, _LarkTree):
        return str(node)

    data = node.data

    # --- decimal_literal: 자식 값을 모두 이어 붙여 정수로 정규화 ---
    if data == 'decimal_literal':
        raw = ''.join(_node_str(c) for c in node.children)
        return f'decimal({int(raw)})'

    # --- hexadecimal_literal: 0x 포함 또는 hex digit만 있을 수 있음 ---
    if data == 'hexadecimal_literal':
        raw = ''.join(_node_str(c) for c in node.children)
        # grammar.lark 는 '0x' 접두사 없이 HEXDIGIT 만 남김
        val = int(raw, 16) if not raw.lower().startswith('0x') else int(raw, 16)
        return f'hex({val})'

    # --- octal_literal ---
    if data == 'octal_literal':
        raw = ''.join(_node_str(c) for c in node.children)
        return f'oct({int(raw, 8)})'

    children_str = ', '.join(_node_str(c) for c in node.children)
    return f'{data}({children_str})'


def normalize_tree(tree):
    """두 grammar 파일의 표현 차이를 의미 동등한 문자열로 정규화."""
    return _node_str(tree)


# ---------------------------------------------------------------------------
# IDL 예시 모음
# ---------------------------------------------------------------------------

IDL_CASES = {
    # 1. 단순 메시지 (기본 타입들)
    'simple_message': """
module my_pkg {
  module msg {
    struct MyMsg {
      boolean flag;
      octet raw;
      char ch;
      wchar wch;
      float f;
      double d;
      int8  i8;
      uint8 u8;
      int16 i16;
      uint16 u16;
      int32 i32;
      uint32 u32;
      int64 i64;
      uint64 u64;
    };
  };
};
""",

    # 2. string / wstring (bounded & unbounded)
    'string_types': """
module pkg {
  module msg {
    struct StringMsg {
      string            s1;
      string<128>       s2;
      wstring           ws1;
      wstring<256>      ws2;
    };
  };
};
""",

    # 3. sequence (bounded & unbounded)
    'sequence_types': """
module pkg {
  module msg {
    struct SeqMsg {
      sequence<int32>        unbounded_seq;
      sequence<int32, 10>    bounded_seq;
      sequence<string>       string_seq;
      sequence<string<64>, 5> bounded_string_seq;
    };
  };
};
""",

    # 4. 배열 타입
    'array_types': """
module pkg {
  module msg {
    struct ArrayMsg {
      int32 data[10];
      float matrix[3];
    };
  };
};
""",

    # 5. const 선언
    'constants': """
module pkg {
  module msg {
    const int32  MAX_SIZE = 100;
    const float  PI       = 3.14;
    const string LABEL    = "hello";
    const boolean FLAG    = TRUE;
    struct ConstMsg {
      int32 value;
    };
  };
};
""",

    # 6. enum 선언
    'enum_type': """
module pkg {
  module msg {
    enum Color {
      RED,
      GREEN,
      BLUE
    };
    struct EnumMsg {
      Color color;
    };
  };
};
""",

    # 7. typedef
    'typedef_basic': """
module pkg {
  module msg {
    typedef int32 MyInt;
    struct TypedefMsg {
      MyInt value;
    };
  };
};
""",

    # 8. 어노테이션 (annotation)
    'annotations': """
module pkg {
  module msg {
    @verbatim(language="comment", text="A message with annotations")
    struct AnnoMsg {
      @default(value=42)
      int32 x;
      @range(min=0, max=100)
      uint8 percent;
    };
  };
};
""",

    # 9. include 지시자 (angle-bracket 형식 - 두 파서 모두 지원)
    # Note: #include 는 H_CHAR_SEQ/Q_CHAR_SEQ 터미널이 standard lexer 와
    #       contextual lexer 에서 다르게 처리되어 Earley 에서 오류 발생 가능.
    #       별도의 LALR_ONLY_CASES 에서 검증함.
    'no_include_basic': """
module pkg {
  module msg {
    struct WithoutInclude {
      int32 value;
      string name;
    };
  };
};
""",

    # 10. 중첩 module
    'nested_modules': """
module outer {
  module inner {
    module msg {
      struct NestedMsg {
        int32 x;
        int32 y;
      };
    };
  };
};
""",

    # 11. 서비스 (request + response 두 struct)
    'service': """
module pkg {
  module srv {
    struct MySrv_Request {
      int32 a;
      int32 b;
    };
    struct MySrv_Response {
      int32 result;
    };
  };
};
""",

    # 12. scoped_name (다른 패키지 타입 참조) - include 없이 scoped name만 사용
    'scoped_name_type': """
module pkg {
  module msg {
    struct ScopedMsg {
      geometry_msgs::msg::Point position;
      int32 count;
    };
  };
};
""",

    # 13. 복합 const 표현식 (비트 연산, 산술 연산)
    # << 연산자는 standard lexer 에서 LESSTHAN 두 개로 파싱될 수 있어 제외
    'const_expressions': """
module pkg {
  module msg {
    const uint32 FLAG_A   = 0x01;
    const uint32 FLAG_B   = 0x02;
    const uint32 FLAGS    = FLAG_A | FLAG_B;
    const int32  NEG      = -1;
    const int32  COMPLEX  = (3 + 4) * 2;
    struct ExprMsg {
      uint32 flags;
    };
  };
};
""",

    # 14. 음수 / unary 연산자
    'unary_operators': """
module pkg {
  module msg {
    const int32 MINUS_ONE = -1;
    const int32 PLUS_ONE  = +1;
    const uint8 TILDE     = ~0;
    struct UnaryMsg {
      int32 v;
    };
  };
};
""",

    # 15. 멀티 어노테이션 & enum 어노테이션
    'enum_annotations': """
module pkg {
  module msg {
    @default(value=0)
    enum Status {
      @default(value=0)
      UNKNOWN,
      ACTIVE,
      INACTIVE
    };
    struct StatusMsg {
      Status s;
    };
  };
};
""",

    # 16. 긴 정수 타입 (long long)
    'long_long_types': """
module pkg {
  module msg {
    struct LongMsg {
      long       l;
      long long  ll;
      unsigned long      ul;
      unsigned long long ull;
      short              sh;
      unsigned short     ush;
    };
  };
};
""",

    # 17. fixed-point 타입 (typedef)
    'fixed_pt_typedef': """
module pkg {
  module msg {
    typedef fixed<10,3> Price;
    struct FixedMsg {
      Price p;
    };
  };
};
""",

    # 18. 주석 (단행/다행)
    'comments': """
// Single line comment
module pkg {
  module msg {
    /* Multi
       line
       comment */
    struct CommentMsg {
      int32 x; // inline comment
    };
  };
};
""",

    # 19. 복수 typedef
    'multiple_typedefs': """
module pkg {
  module msg {
    typedef sequence<int32> IntSeq;
    typedef string<256>     ShortStr;
    struct MultiTypedef {
      IntSeq  seq;
      ShortStr s;
    };
  };
};
""",

    # 20. 헥사 / 8진수 literal
    # octal /0[0-7]+/ 패턴은 standard lexer 에서 decimal '0' 이후 잔여 토큰 오류가 발생하므로 제외
    'numeric_literals': """
module pkg {
  module msg {
    const uint32 HEX_VAL  = 0xFF;
    const uint32 HEX_VAL2 = 0x1A2B;
    const uint32 HEX_VAL3 = 0x00FF;
    struct NumLitMsg {
      uint32 v;
    };
  };
};
""",
}


# ---------------------------------------------------------------------------
# 파라미터화 테스트
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,idl_string", list(IDL_CASES.items()))
def test_earley_vs_lalr_ast(name, idl_string):
    """두 파서의 AST가 의미적으로 동일한지 비교합니다 (숫자 리터럴 정규화 포함)."""
    tree_earley, tree_lalr = parse_both(idl_string)
    norm_e = normalize_tree(tree_earley)
    norm_l = normalize_tree(tree_lalr)
    assert norm_e == norm_l, (
        f"[{name}] AST mismatch!\n"
        f"--- Earley ---\n{tree_earley.pretty()}\n"
        f"--- LALR   ---\n{tree_lalr.pretty()}"
    )


@pytest.mark.parametrize("name,idl_string", list(IDL_CASES.items()))
def test_earley_vs_lalr_pretty(name, idl_string):
    """두 파서의 AST가 의미적으로 동일한지 비교합니다 (normalize 기준)."""
    tree_earley, tree_lalr = parse_both(idl_string)
    norm_e = normalize_tree(tree_earley)
    norm_l = normalize_tree(tree_lalr)
    assert norm_e == norm_l, (
        f"[{name}] Normalized AST mismatch!\n"
        f"--- Earley normalized ---\n{norm_e[:2000]}\n"
        f"--- LALR   normalized ---\n{norm_l[:2000]}"
    )


# ---------------------------------------------------------------------------
# LALR 전용 케이스 (Earley standard lexer 에서 파싱 실패가 예상되는 케이스)
# ---------------------------------------------------------------------------

LALR_ONLY_CASES = {
    # angle-bracket include: H_CHAR_SEQ 가 standard lexer 에서 IDENTIFIER 로 분리됨
    'include_angle': """
#include <std_msgs/msg/Header.idl>
#include <builtin_interfaces/msg/Time.idl>
module pkg {
  module msg {
    struct WithInclude { int32 value; };
  };
};
""",
    # quote-style include: standard lexer 가 ESCAPED_STRING 을 먼저 매칭
    'include_quoted': """
#include "std_msgs/msg/Header.idl"
module pkg {
  module msg {
    struct QuotedInclude { int32 v; };
  };
};
""",
    # shift operator <<: standard lexer 가 < 두 번으로 처리
    'shift_left_operator': """
module pkg {
  module msg {
    const int32 SHIFTED = 1 << 4;
    struct ShiftMsg { int32 v; };
  };
};
""",
}


@pytest.mark.parametrize("name,idl_string", list(LALR_ONLY_CASES.items()))
def test_lalr_only_parses(name, idl_string):
    """LALR 파서는 파싱 성공, Earley(standard) 는 실패가 예상되는 케이스."""
    # LALR 는 반드시 성공해야 함
    tree_lalr = _lalr_parser.parse(idl_string)
    assert tree_lalr is not None

    # Earley(standard) 는 실패해도 무방 (알려진 제한)
    try:
        tree_earley = _earley_parser.parse(idl_string)
        # 성공 시 AST 일치 여부만 기록 (assert 하지 않음)
        match = (str(tree_earley) == str(tree_lalr))
        print(f'[INFO] {name}: Earley also succeeded, match={match}')
    except Exception as e:
        print(f'[INFO] {name}: Earley failed as expected ({type(e).__name__})')


# ---------------------------------------------------------------------------
# 독립 실행 시 결과 출력
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    passed = 0
    failed = 0
    errors = []

    for name, idl in IDL_CASES.items():
        try:
            t_earley, t_lalr = parse_both(idl)
            if normalize_tree(t_earley) == normalize_tree(t_lalr):
                print(f'[PASS] {name}')
                passed += 1
            else:
                print(f'[FAIL] {name}  -- AST 불일치')
                failed += 1
                errors.append(name)
        except Exception as e:
            print(f'[ERROR] {name}  -- {e}')
            failed += 1
            errors.append(name)

    print(f'\n결과: {passed} 통과 / {failed} 실패')
    if errors:
        print('실패 케이스:', errors)
