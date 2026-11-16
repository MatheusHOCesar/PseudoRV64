"""Ponto de implementação das regras declarativas do enunciado."""

import load_previous
from ast_nodes import (
    BinaryExpr,
    BinaryOperator,
    BoolLiteral,
    CallExpr,
    IdentifierExpr,
    TypeName,
    UnaryExpr,
    UnaryOperator,
)
from patterns import (
    COND,
    EFFECT,
    IMM12,
    POW2,
    REG,
    Args,
    Need,
    Pattern,
    Rule,
    imm12,
    neg_imm12,
    pow2,
    signed_literal,
)


def is_signed_int_literal(node):
    """Reconheça literal inteiro com sinal dentro do limite de 64 bits."""
    val = signed_literal(node)
    return val is not None and -(1 << 63) <= val <= (1 << 63) - 1


def is_bool_expr(node):
    """Verifique se o nó possui tipo bool anotado (ou sem anotação em testes sintéticos)."""
    t = node.metadata.get("type")
    if t is not None:
        return t == TypeName.BOOL
    sym = node.metadata.get("symbol")
    if sym is not None and hasattr(sym, "type"):
        return sym.type == TypeName.BOOL
    return True


def is_non_void_call(node):
    """Garanta que chamadas void ofereçam apenas EFFECT, não REG."""
    t = node.metadata.get("type")
    if t is not None:
        return t != TypeName.VOID
    sym = node.metadata.get("symbol")
    if sym is not None and hasattr(sym, "type"):
        return sym.type != TypeName.VOID
    return True


def catalogue():
    """Codifique o catálogo do enunciado com Rule e Pattern."""
    return [
        # 1. Literal inteiro com sinal ou bool para REG, com Li (custo 1)
        Rule(
            name="int_literal_reg",
            result=REG,
            pattern=Pattern(predicate=is_signed_int_literal),
            cost=1,
            action="emit_int_literal_reg",
        ),
        Rule(
            name="bool_literal_reg",
            result=REG,
            pattern=Pattern(kind=BoolLiteral),
            cost=1,
            action="emit_bool_literal_reg",
        ),
        # 2. Identificador para REG, reutilizando o VReg do símbolo (custo 0)
        Rule(
            name="identifier_reg",
            result=REG,
            pattern=Pattern(kind=IdentifierExpr),
            cost=0,
            action="emit_identifier_reg",
        ),
        # 3. Literal elegível para IMM12 ou POW2, sem instrução (custo 0)
        Rule(
            name="literal_imm12",
            result=IMM12,
            pattern=Pattern(predicate=imm12),
            cost=0,
            action="emit_literal_imm12",
        ),
        Rule(
            name="literal_pow2",
            result=POW2,
            pattern=Pattern(predicate=pow2),
            cost=0,
            action="emit_literal_pow2",
        ),
        # 4. Negação aritmética de REG para REG, com Neg (custo 1)
        Rule(
            name="neg_reg",
            result=REG,
            pattern=Pattern(
                kind=UnaryExpr,
                operator=UnaryOperator.NEGATE,
                children=(Need(REG),),
            ),
            cost=1,
            action="emit_neg_reg",
        ),
        # 5. Aritmética geral de dois REG para REG (custo 1)
        Rule(
            name="add_reg",
            result=REG,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.ADD,
                children=(Need(REG), Need(REG)),
            ),
            cost=1,
            action="emit_add_reg",
        ),
        Rule(
            name="sub_reg",
            result=REG,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.SUBTRACT,
                children=(Need(REG), Need(REG)),
            ),
            cost=1,
            action="emit_sub_reg",
        ),
        Rule(
            name="mul_reg",
            result=REG,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.MULTIPLY,
                children=(Need(REG), Need(REG)),
            ),
            cost=1,
            action="emit_mul_reg",
        ),
        Rule(
            name="div_reg",
            result=REG,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.DIVIDE,
                children=(Need(REG), Need(REG)),
            ),
            cost=1,
            action="emit_div_reg",
        ),
        Rule(
            name="rem_reg",
            result=REG,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.REMAINDER,
                children=(Need(REG), Need(REG)),
            ),
            cost=1,
            action="emit_rem_reg",
        ),
        # 6. Soma REG/IMM12 ou IMM12/REG, com Addi (custo 1)
        Rule(
            name="add_reg_imm12",
            result=REG,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.ADD,
                children=(Need(REG), Need(IMM12)),
            ),
            cost=1,
            action="emit_add_reg_imm12",
        ),
        Rule(
            name="add_imm12_reg",
            result=REG,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.ADD,
                children=(Need(IMM12), Need(REG)),
            ),
            cost=1,
            action="emit_add_imm12_reg",
        ),
        # 7. Subtração REG menos literal cujo oposto cabe no imediato, com Addi (custo 1)
        Rule(
            name="sub_reg_neg_imm12",
            result=REG,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.SUBTRACT,
                children=(Need(REG), Pattern(predicate=neg_imm12)),
            ),
            cost=1,
            action="emit_sub_reg_neg_imm12",
        ),
        # 8. Multiplicação REG/POW2 ou POW2/REG, com Slli (custo 1)
        Rule(
            name="mul_reg_pow2",
            result=REG,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.MULTIPLY,
                children=(Need(REG), Need(POW2)),
            ),
            cost=1,
            action="emit_mul_reg_pow2",
        ),
        Rule(
            name="mul_pow2_reg",
            result=REG,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.MULTIPLY,
                children=(Need(POW2), Need(REG)),
            ),
            cost=1,
            action="emit_mul_pow2_reg",
        ),
        # 9. Menor ou maior de dois REG para REG, com Slt (custo 1)
        Rule(
            name="lt_reg",
            result=REG,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.LESS,
                children=(Need(REG), Need(REG)),
            ),
            cost=1,
            action="emit_lt_reg",
        ),
        Rule(
            name="gt_reg",
            result=REG,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.GREATER,
                children=(Need(REG), Need(REG)),
            ),
            cost=1,
            action="emit_gt_reg",
        ),
        # 10. Menor ou igual, maior ou igual para REG, com Slt e Seqz (custo 2)
        Rule(
            name="le_reg",
            result=REG,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.LESS_EQUAL,
                children=(Need(REG), Need(REG)),
            ),
            cost=2,
            action="emit_le_reg",
        ),
        Rule(
            name="ge_reg",
            result=REG,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.GREATER_EQUAL,
                children=(Need(REG), Need(REG)),
            ),
            cost=2,
            action="emit_ge_reg",
        ),
        # 11. Igualdade/desigualdade para REG, com Xor e Seqz/Snez (custo 2)
        Rule(
            name="eq_reg",
            result=REG,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.EQUAL,
                children=(Need(REG), Need(REG)),
            ),
            cost=2,
            action="emit_eq_reg",
        ),
        Rule(
            name="ne_reg",
            result=REG,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.NOT_EQUAL,
                children=(Need(REG), Need(REG)),
            ),
            cost=2,
            action="emit_ne_reg",
        ),
        # 12. Comparação de dois REG para COND, branch direto e Jump (custo 2)
        Rule(
            name="lt_cond",
            result=COND,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.LESS,
                children=(Need(REG), Need(REG)),
            ),
            cost=2,
            action="emit_lt_cond",
        ),
        Rule(
            name="le_cond",
            result=COND,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.LESS_EQUAL,
                children=(Need(REG), Need(REG)),
            ),
            cost=2,
            action="emit_le_cond",
        ),
        Rule(
            name="gt_cond",
            result=COND,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.GREATER,
                children=(Need(REG), Need(REG)),
            ),
            cost=2,
            action="emit_gt_cond",
        ),
        Rule(
            name="ge_cond",
            result=COND,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.GREATER_EQUAL,
                children=(Need(REG), Need(REG)),
            ),
            cost=2,
            action="emit_ge_cond",
        ),
        Rule(
            name="eq_cond",
            result=COND,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.EQUAL,
                children=(Need(REG), Need(REG)),
            ),
            cost=2,
            action="emit_eq_cond",
        ),
        Rule(
            name="ne_cond",
            result=COND,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.NOT_EQUAL,
                children=(Need(REG), Need(REG)),
            ),
            cost=2,
            action="emit_ne_cond",
        ),
        # 13. Negação lógica de REG para REG, com Seqz (custo 1)
        Rule(
            name="not_reg",
            result=REG,
            pattern=Pattern(
                kind=UnaryExpr,
                operator=UnaryOperator.NOT,
                children=(Need(REG),),
            ),
            cost=1,
            action="emit_not_reg",
        ),
        # 14. Negação lógica de COND para COND, invertendo destinos (custo 0)
        Rule(
            name="not_cond",
            result=COND,
            pattern=Pattern(
                kind=UnaryExpr,
                operator=UnaryOperator.NOT,
                children=(Need(COND),),
            ),
            cost=0,
            action="emit_not_cond",
        ),
        # 15. && / || de dois COND para COND (custo 0)
        Rule(
            name="and_cond",
            result=COND,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.LOGICAL_AND,
                children=(Need(COND), Need(COND)),
            ),
            cost=0,
            action="emit_and_cond",
        ),
        Rule(
            name="or_cond",
            result=COND,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.LOGICAL_OR,
                children=(Need(COND), Need(COND)),
            ),
            cost=0,
            action="emit_or_cond",
        ),
        # 16. && / || de dois COND para REG, com duas Li e um Jump (custo 3)
        Rule(
            name="and_reg",
            result=REG,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.LOGICAL_AND,
                children=(Need(COND), Need(COND)),
            ),
            cost=3,
            action="emit_and_reg",
        ),
        Rule(
            name="or_reg",
            result=REG,
            pattern=Pattern(
                kind=BinaryExpr,
                operator=BinaryOperator.LOGICAL_OR,
                children=(Need(COND), Need(COND)),
            ),
            cost=3,
            action="emit_or_reg",
        ),
        # 17. Literal bool para COND, com Jump (custo 1)
        Rule(
            name="bool_literal_cond",
            result=COND,
            pattern=Pattern(kind=BoolLiteral),
            cost=1,
            action="emit_bool_literal_cond",
        ),
        # 18. Identificador bool para COND, com branch e Jump (custo 2)
        Rule(
            name="identifier_cond",
            result=COND,
            pattern=Pattern(kind=IdentifierExpr, predicate=is_bool_expr),
            cost=2,
            action="emit_identifier_cond",
        ),
        # 19. Chamada com argumentos REG para REG ou EFFECT, com Call (custo 1)
        Rule(
            name="call_reg",
            result=REG,
            pattern=Pattern(
                kind=CallExpr,
                children=(Args(REG),),
                predicate=is_non_void_call,
            ),
            cost=1,
            action="emit_call_reg",
        ),
        Rule(
            name="call_effect",
            result=EFFECT,
            pattern=Pattern(
                kind=CallExpr,
                children=(Args(REG),),
            ),
            cost=1,
            action="emit_call_effect",
        ),
        # 20. Chamada bool com argumentos REG para COND, com chamada e desvios (custo 3)
        Rule(
            name="call_cond",
            result=COND,
            pattern=Pattern(
                kind=CallExpr,
                children=(Args(REG),),
                predicate=is_bool_expr,
            ),
            cost=3,
            action="emit_call_cond",
        ),
    ]