"""Ponto de implementação do reconhecimento de padrões e custos mínimos."""

from patterns import *


class Selector:
    """Selecione coberturas sem executar expressões ou emitir instruções."""

    def __init__(self, rules):
        self.rules = tuple(rules)

    def analyze(self, expr):
        """Calcule mínimos por nó/classe sem emitir instruções."""
        table = SelectionTable()
        self._postorder(expr, table)
        return table

    def _postorder(self, node, table):
        for child in children(node):
            self._postorder(child, table)

        for rule in self.rules:
            subproblems = self._match_pattern(rule.pattern, node)
            if subproblems is None:
                continue

            total_cost = rule.cost
            possible = True
            for sub_node, req_class in subproblems:
                sub_choice = table.lookup(sub_node, req_class)
                if sub_choice is None:
                    possible = False
                    break
                total_cost += sub_choice.cost

            if not possible:
                continue

            current = table.lookup(node, rule.result)
            if current is None or total_cost < current.cost:
                table.put(node, rule.result, Choice(total_cost, rule, subproblems))

    def _match_pattern(self, pattern, node):
        """Retorne a tupla de subproblemas (nó, classe) se o padrão casar, ou None."""
        if pattern.kind is not None and not isinstance(node, pattern.kind):
            return None

        if pattern.operator is not None:
            if getattr(node, "operator", None) != pattern.operator:
                return None

        if pattern.predicate is not None and not pattern.predicate(node):
            return None

        node_children = children(node)
        pat_children = pattern.children

        # Caso especial: um padrão com predicado e sem filhos reconhece a subárvore
        # inteira quando esse predicado é verdadeiro (ex: signed_literal em UnaryExpr).
        if not pat_children and pattern.predicate is not None:
            return ()

        # Caso especial: Args(classe) como único filho do padrão de uma chamada
        if len(pat_children) == 1 and isinstance(pat_children[0], Args):
            req_class = pat_children[0].result
            return tuple((child, req_class) for child in node_children)

        if len(pat_children) != len(node_children):
            return None

        subproblems = []
        for pat_child, ast_child in zip(pat_children, node_children):
            if isinstance(pat_child, Need):
                subproblems.append((ast_child, pat_child.result))
            elif isinstance(pat_child, Pattern):
                nested = self._match_pattern(pat_child, ast_child)
                if nested is None:
                    return None
                subproblems.extend(nested)
            else:
                return None

        return tuple(subproblems)