"""Pontos de implementação da geração de comandos e expressões."""

import load_previous
import ir as I
from ir import Context, ProgramIR, FunctionIR
from ast_nodes import (
    Assignment,
    Block,
    CallStmt,
    FunctionDecl,
    IfStmt,
    PrintStmt,
    Program,
    ReturnStmt,
    StringLiteral,
    TypeName,
    VarDecl,
    WhileStmt,
)
from catalogue import catalogue
from patterns import COND, EFFECT, IMM12, POW2, REG, pow2, signed_literal
from selector import Selector


class CodeGenerator:
    """Coordene comandos ad hoc e seleção de expressões com DP."""

    def __init__(self, rules=None):
        self.rules = catalogue() if rules is None else tuple(rules)
        self.selector = Selector(self.rules)
        self.ctx = None

    def generate(self, program: Program) -> ProgramIR:
        """Traduza funções e comandos. Selecione expressões com DP."""
        program_ir = ProgramIR()
        prev_ctx = self.ctx
        try:
            for fn_decl in program.functions:
                fn_sym = fn_decl.metadata["symbol"]
                fn_ir = FunctionIR(fn_sym)
                program_ir.functions.append(fn_ir)
                self.ctx = Context(fn_ir, program_ir)

                # Emitir Param para cada parâmetro no início da lista, em ordem
                for idx, param in enumerate(fn_decl.parameters):
                    param_sym = param.metadata["symbol"]
                    vreg = self.ctx.variable(param_sym)
                    self.ctx.emit(I.Param(vreg, idx, origin=param.span))

                # Traduzir corpo da função
                self.statement(fn_decl.body)

                # Fim normal de função void deve ter Return(None)
                if fn_decl.return_type == TypeName.VOID:
                    if not fn_ir.instructions or not isinstance(
                        fn_ir.instructions[-1], I.Return
                    ):
                        self.ctx.emit(I.Return(None, origin=fn_decl.span))
        finally:
            self.ctx = prev_ctx

        return program_ir

    def statement(self, node):
        """Traduza um comando ad hoc."""
        if isinstance(node, Block):
            for stmt in node.statements:
                self.statement(stmt)

        elif isinstance(node, VarDecl):
            sym = node.metadata["symbol"]
            if node.initializer is not None:
                val_reg = self.expression(node.initializer, REG)
                dst_reg = self.ctx.variable(sym)
                self.ctx.emit(I.Move(dst_reg, val_reg, origin=node.span))

        elif isinstance(node, Assignment):
            sym = node.target.metadata["symbol"]
            val_reg = self.expression(node.value, REG)
            dst_reg = self.ctx.variable(sym)
            self.ctx.emit(I.Move(dst_reg, val_reg, origin=node.span))

        elif isinstance(node, CallStmt):
            self.expression(node.call, EFFECT)

        elif isinstance(node, ReturnStmt):
            if node.value is None:
                self.ctx.emit(I.Return(None, origin=node.span))
            else:
                val_reg = self.expression(node.value, REG)
                self.ctx.emit(I.Return(val_reg, origin=node.span))

        elif isinstance(node, PrintStmt):
            for item in node.items:
                if isinstance(item, StringLiteral):
                    str_ref = self.ctx.string(item.value)
                    self.ctx.emit(I.PrintString(str_ref, origin=item.span))
                else:
                    val_reg = self.expression(item, REG)
                    item_type = item.metadata.get("type")
                    if item_type == TypeName.BOOL:
                        self.ctx.emit(I.PrintBool(val_reg, origin=item.span))
                    else:
                        self.ctx.emit(I.PrintInt(val_reg, origin=item.span))

            newline_ref = self.ctx.string("\n")
            self.ctx.emit(I.PrintString(newline_ref, origin=node.span))

        elif isinstance(node, IfStmt):
            then_label = self.ctx.label()
            if node.else_block is not None:
                else_label = self.ctx.label()
                end_label = self.ctx.label()
                self.expression(
                    node.condition, COND, true_label=then_label, false_label=else_label
                )
                self.ctx.emit(I.LabelInstr(then_label, origin=node.then_block.span))
                self.statement(node.then_block)
                self.ctx.emit(I.Jump(end_label, origin=node.span))
                self.ctx.emit(I.LabelInstr(else_label, origin=node.else_block.span))
                self.statement(node.else_block)
                self.ctx.emit(I.LabelInstr(end_label, origin=node.span))
            else:
                end_label = self.ctx.label()
                self.expression(
                    node.condition, COND, true_label=then_label, false_label=end_label
                )
                self.ctx.emit(I.LabelInstr(then_label, origin=node.then_block.span))
                self.statement(node.then_block)
                self.ctx.emit(I.LabelInstr(end_label, origin=node.span))

        elif isinstance(node, WhileStmt):
            test_label = self.ctx.label()
            body_label = self.ctx.label()
            end_label = self.ctx.label()
            self.ctx.emit(I.LabelInstr(test_label, origin=node.span))
            self.expression(
                node.condition, COND, true_label=body_label, false_label=end_label
            )
            self.ctx.emit(I.LabelInstr(body_label, origin=node.body.span))
            self.statement(node.body)
            self.ctx.emit(I.Jump(test_label, origin=node.span))
            self.ctx.emit(I.LabelInstr(end_label, origin=node.span))

        else:
            raise ValueError(f"Comando desconhecido: {type(node).__name__}")

    def expression(self, node, result_class, true_label=None, false_label=None):
        """Selecione e reconstrua uma expressão, preservando curto-circuito."""
        table = self.selector.analyze(node)
        choice = table.lookup(node, result_class)
        if choice is None:
            span = getattr(node, "span", None)
            pos = (
                f" na linha {span.start_line}, coluna {span.start_column}"
                if span is not None
                else ""
            )
            raise ValueError(
                f"Sem cobertura para {type(node).__name__} na classe {result_class}{pos}"
            )
        return self._emit_choice(node, result_class, table, true_label, false_label)

    def _emit_choice(self, node, result_class, table, true_label=None, false_label=None):
        choice = table.lookup(node, result_class)
        if choice is None:
            span = getattr(node, "span", None)
            pos = (
                f" na linha {span.start_line}, coluna {span.start_column}"
                if span is not None
                else ""
            )
            raise ValueError(
                f"Sem cobertura para {type(node).__name__} na classe {result_class}{pos}"
            )

        action_name = choice.rule.action
        method = getattr(self, f"_{action_name}", None)
        if method is None:
            raise ValueError(f"Ação emissora não implementada: {action_name}")
        return method(node, choice, table, true_label, false_label)

    def _eval_subproblems(self, choice, table):
        """Avalie todos os subproblemas na ordem da fonte (para regras sem curto-circuito)."""
        return [
            self._emit_choice(sub_node, sub_class, table)
            for sub_node, sub_class in choice.subproblems
        ]

    # --- Ações para Folhas e Literais ---

    def _emit_int_literal_reg(self, node, choice, table, true_label, false_label):
        val = signed_literal(node)
        dst = self.ctx.temp()
        self.ctx.emit(I.Li(dst, val, origin=node.span))
        return dst

    def _emit_bool_literal_reg(self, node, choice, table, true_label, false_label):
        dst = self.ctx.temp()
        self.ctx.emit(I.Li(dst, 1 if node.value else 0, origin=node.span))
        return dst

    def _emit_identifier_reg(self, node, choice, table, true_label, false_label):
        sym = node.metadata["symbol"]
        return self.ctx.variable(sym)

    def _emit_literal_imm12(self, node, choice, table, true_label, false_label):
        return signed_literal(node)

    def _emit_literal_pow2(self, node, choice, table, true_label, false_label):
        val = signed_literal(node)
        return val.bit_length() - 1

    # --- Ações Aritméticas ---

    def _emit_neg_reg(self, node, choice, table, true_label, false_label):
        (src,) = self._eval_subproblems(choice, table)
        dst = self.ctx.temp()
        self.ctx.emit(I.Neg(dst, src, origin=node.span))
        return dst

    def _emit_add_reg(self, node, choice, table, true_label, false_label):
        lhs, rhs = self._eval_subproblems(choice, table)
        dst = self.ctx.temp()
        self.ctx.emit(I.Add(dst, lhs, rhs, origin=node.span))
        return dst

    def _emit_sub_reg(self, node, choice, table, true_label, false_label):
        lhs, rhs = self._eval_subproblems(choice, table)
        dst = self.ctx.temp()
        self.ctx.emit(I.Sub(dst, lhs, rhs, origin=node.span))
        return dst

    def _emit_mul_reg(self, node, choice, table, true_label, false_label):
        lhs, rhs = self._eval_subproblems(choice, table)
        dst = self.ctx.temp()
        self.ctx.emit(I.Mul(dst, lhs, rhs, origin=node.span))
        return dst

    def _emit_div_reg(self, node, choice, table, true_label, false_label):
        lhs, rhs = self._eval_subproblems(choice, table)
        dst = self.ctx.temp()
        self.ctx.emit(I.Div(dst, lhs, rhs, origin=node.span))
        return dst

    def _emit_rem_reg(self, node, choice, table, true_label, false_label):
        lhs, rhs = self._eval_subproblems(choice, table)
        dst = self.ctx.temp()
        self.ctx.emit(I.Rem(dst, lhs, rhs, origin=node.span))
        return dst

    def _emit_add_reg_imm12(self, node, choice, table, true_label, false_label):
        reg_val, imm_val = self._eval_subproblems(choice, table)
        dst = self.ctx.temp()
        self.ctx.emit(I.Addi(dst, reg_val, imm_val, origin=node.span))
        return dst

    def _emit_add_imm12_reg(self, node, choice, table, true_label, false_label):
        imm_val, reg_val = self._eval_subproblems(choice, table)
        dst = self.ctx.temp()
        self.ctx.emit(I.Addi(dst, reg_val, imm_val, origin=node.span))
        return dst

    def _emit_sub_reg_neg_imm12(self, node, choice, table, true_label, false_label):
        (reg_val,) = self._eval_subproblems(choice, table)
        imm_val = -signed_literal(node.right)
        dst = self.ctx.temp()
        self.ctx.emit(I.Addi(dst, reg_val, imm_val, origin=node.span))
        return dst

    def _emit_mul_reg_pow2(self, node, choice, table, true_label, false_label):
        reg_val, shift = self._eval_subproblems(choice, table)
        dst = self.ctx.temp()
        self.ctx.emit(I.Slli(dst, reg_val, shift, origin=node.span))
        return dst

    def _emit_mul_pow2_reg(self, node, choice, table, true_label, false_label):
        shift, reg_val = self._eval_subproblems(choice, table)
        dst = self.ctx.temp()
        self.ctx.emit(I.Slli(dst, reg_val, shift, origin=node.span))
        return dst

    # --- Ações Relacionais e de Igualdade para REG ---

    def _emit_lt_reg(self, node, choice, table, true_label, false_label):
        lhs, rhs = self._eval_subproblems(choice, table)
        dst = self.ctx.temp()
        self.ctx.emit(I.Slt(dst, lhs, rhs, origin=node.span))
        return dst

    def _emit_gt_reg(self, node, choice, table, true_label, false_label):
        lhs, rhs = self._eval_subproblems(choice, table)
        dst = self.ctx.temp()
        self.ctx.emit(I.Slt(dst, rhs, lhs, origin=node.span))
        return dst

    def _emit_le_reg(self, node, choice, table, true_label, false_label):
        lhs, rhs = self._eval_subproblems(choice, table)
        tmp = self.ctx.temp()
        dst = self.ctx.temp()
        self.ctx.emit(I.Slt(tmp, rhs, lhs, origin=node.span))
        self.ctx.emit(I.Seqz(dst, tmp, origin=node.span))
        return dst

    def _emit_ge_reg(self, node, choice, table, true_label, false_label):
        lhs, rhs = self._eval_subproblems(choice, table)
        tmp = self.ctx.temp()
        dst = self.ctx.temp()
        self.ctx.emit(I.Slt(tmp, lhs, rhs, origin=node.span))
        self.ctx.emit(I.Seqz(dst, tmp, origin=node.span))
        return dst

    def _emit_eq_reg(self, node, choice, table, true_label, false_label):
        lhs, rhs = self._eval_subproblems(choice, table)
        tmp = self.ctx.temp()
        dst = self.ctx.temp()
        self.ctx.emit(I.Xor(tmp, lhs, rhs, origin=node.span))
        self.ctx.emit(I.Seqz(dst, tmp, origin=node.span))
        return dst

    def _emit_ne_reg(self, node, choice, table, true_label, false_label):
        lhs, rhs = self._eval_subproblems(choice, table)
        tmp = self.ctx.temp()
        dst = self.ctx.temp()
        self.ctx.emit(I.Xor(tmp, lhs, rhs, origin=node.span))
        self.ctx.emit(I.Snez(dst, tmp, origin=node.span))
        return dst

    # --- Ações Relacionais e de Igualdade para COND ---

    def _emit_lt_cond(self, node, choice, table, true_label, false_label):
        lhs, rhs = self._eval_subproblems(choice, table)
        self.ctx.emit(I.Blt(lhs, rhs, true_label, origin=node.span))
        self.ctx.emit(I.Jump(false_label, origin=node.span))

    def _emit_le_cond(self, node, choice, table, true_label, false_label):
        lhs, rhs = self._eval_subproblems(choice, table)
        self.ctx.emit(I.Bge(rhs, lhs, true_label, origin=node.span))
        self.ctx.emit(I.Jump(false_label, origin=node.span))

    def _emit_gt_cond(self, node, choice, table, true_label, false_label):
        lhs, rhs = self._eval_subproblems(choice, table)
        self.ctx.emit(I.Blt(rhs, lhs, true_label, origin=node.span))
        self.ctx.emit(I.Jump(false_label, origin=node.span))

    def _emit_ge_cond(self, node, choice, table, true_label, false_label):
        lhs, rhs = self._eval_subproblems(choice, table)
        self.ctx.emit(I.Bge(lhs, rhs, true_label, origin=node.span))
        self.ctx.emit(I.Jump(false_label, origin=node.span))

    def _emit_eq_cond(self, node, choice, table, true_label, false_label):
        lhs, rhs = self._eval_subproblems(choice, table)
        self.ctx.emit(I.Beq(lhs, rhs, true_label, origin=node.span))
        self.ctx.emit(I.Jump(false_label, origin=node.span))

    def _emit_ne_cond(self, node, choice, table, true_label, false_label):
        lhs, rhs = self._eval_subproblems(choice, table)
        self.ctx.emit(I.Bne(lhs, rhs, true_label, origin=node.span))
        self.ctx.emit(I.Jump(false_label, origin=node.span))

    # --- Ações Lógicas e Booleanas ---

    def _emit_not_reg(self, node, choice, table, true_label, false_label):
        (src,) = self._eval_subproblems(choice, table)
        dst = self.ctx.temp()
        self.ctx.emit(I.Seqz(dst, src, origin=node.span))
        return dst

    def _emit_not_cond(self, node, choice, table, true_label, false_label):
        (sub_node, sub_class) = choice.subproblems[0]
        self._emit_choice(
            sub_node, sub_class, table, true_label=false_label, false_label=true_label
        )

    def _emit_and_cond(self, node, choice, table, true_label, false_label):
        (left_node, left_class), (right_node, right_class) = choice.subproblems
        mid_label = self.ctx.label()
        self._emit_choice(
            left_node, left_class, table, true_label=mid_label, false_label=false_label
        )
        self.ctx.emit(I.LabelInstr(mid_label, origin=node.span))
        self._emit_choice(
            right_node, right_class, table, true_label=true_label, false_label=false_label
        )

    def _emit_or_cond(self, node, choice, table, true_label, false_label):
        (left_node, left_class), (right_node, right_class) = choice.subproblems
        mid_label = self.ctx.label()
        self._emit_choice(
            left_node, left_class, table, true_label=true_label, false_label=mid_label
        )
        self.ctx.emit(I.LabelInstr(mid_label, origin=node.span))
        self._emit_choice(
            right_node, right_class, table, true_label=true_label, false_label=false_label
        )

    def _emit_and_reg(self, node, choice, table, true_label, false_label):
        (left_node, left_class), (right_node, right_class) = choice.subproblems
        mid_label = self.ctx.label()
        t_label = self.ctx.label()
        f_label = self.ctx.label()
        end_label = self.ctx.label()
        dst = self.ctx.temp()

        self._emit_choice(
            left_node, left_class, table, true_label=mid_label, false_label=f_label
        )
        self.ctx.emit(I.LabelInstr(mid_label, origin=node.span))
        self._emit_choice(
            right_node, right_class, table, true_label=t_label, false_label=f_label
        )
        self.ctx.emit(I.LabelInstr(t_label, origin=node.span))
        self.ctx.emit(I.Li(dst, 1, origin=node.span))
        self.ctx.emit(I.Jump(end_label, origin=node.span))
        self.ctx.emit(I.LabelInstr(f_label, origin=node.span))
        self.ctx.emit(I.Li(dst, 0, origin=node.span))
        self.ctx.emit(I.LabelInstr(end_label, origin=node.span))
        return dst

    def _emit_or_reg(self, node, choice, table, true_label, false_label):
        (left_node, left_class), (right_node, right_class) = choice.subproblems
        mid_label = self.ctx.label()
        t_label = self.ctx.label()
        f_label = self.ctx.label()
        end_label = self.ctx.label()
        dst = self.ctx.temp()

        self._emit_choice(
            left_node, left_class, table, true_label=t_label, false_label=mid_label
        )
        self.ctx.emit(I.LabelInstr(mid_label, origin=node.span))
        self._emit_choice(
            right_node, right_class, table, true_label=t_label, false_label=f_label
        )
        self.ctx.emit(I.LabelInstr(t_label, origin=node.span))
        self.ctx.emit(I.Li(dst, 1, origin=node.span))
        self.ctx.emit(I.Jump(end_label, origin=node.span))
        self.ctx.emit(I.LabelInstr(f_label, origin=node.span))
        self.ctx.emit(I.Li(dst, 0, origin=node.span))
        self.ctx.emit(I.LabelInstr(end_label, origin=node.span))
        return dst

    def _emit_bool_literal_cond(self, node, choice, table, true_label, false_label):
        target = true_label if node.value else false_label
        self.ctx.emit(I.Jump(target, origin=node.span))

    def _emit_identifier_cond(self, node, choice, table, true_label, false_label):
        sym = node.metadata["symbol"]
        vreg = self.ctx.variable(sym)
        self.ctx.emit(I.Bnez(vreg, true_label, origin=node.span))
        self.ctx.emit(I.Jump(false_label, origin=node.span))

    # --- Ações para Chamadas ---

    def _emit_call_reg(self, node, choice, table, true_label, false_label):
        args = self._eval_subproblems(choice, table)
        fn_sym = node.metadata["symbol"]
        dst = self.ctx.temp()
        self.ctx.emit(I.Call(dst, fn_sym, args, origin=node.span))
        return dst

    def _emit_call_effect(self, node, choice, table, true_label, false_label):
        args = self._eval_subproblems(choice, table)
        fn_sym = node.metadata["symbol"]
        self.ctx.emit(I.Call(None, fn_sym, args, origin=node.span))
        return None

    def _emit_call_cond(self, node, choice, table, true_label, false_label):
        args = self._eval_subproblems(choice, table)
        fn_sym = node.metadata["symbol"]
        dst = self.ctx.temp()
        self.ctx.emit(I.Call(dst, fn_sym, args, origin=node.span))
        self.ctx.emit(I.Bnez(dst, true_label, origin=node.span))
        self.ctx.emit(I.Jump(false_label, origin=node.span))