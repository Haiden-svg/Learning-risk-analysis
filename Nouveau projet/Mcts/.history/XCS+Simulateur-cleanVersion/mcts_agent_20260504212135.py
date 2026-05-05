import random
import math
from typing import List, Optional

# --- Classe pour représenter un nœud de l'arbre MCTS ---
class MCTSNode:
    def __init__(self, state_loc, state_secr, current_cost, parent=None, action=None):
        self.state_loc = state_loc.copy()
        self.state_secr = state_secr.copy()
        self.current_cost = current_cost
        
        self.parent = parent
        self.action = action  # L'action (ActiveTransition) qui a mené à ce nœud
        self.children = []
        
        self.untried_actions = [] 
        
        self.visits = 0
        self.score = 0.0 # Score de réussite de l'attaque
        
    def is_fully_expanded(self):
        return len(self.untried_actions) == 0 and len(self.children) > 0


# --- Classe Principale de l'Agent MCTS ---
class MCTSAgent:
    def __init__(self, env, maxCost, num_iterations=1000, exploration_constant=1.41):
        self.env = env
        self.maxCost = maxCost
        self.num_iterations = num_iterations
        self.exploration_constant = exploration_constant

    def selectAction(self, maxCost, step, stat=False):
        # 1. Sauvegarder l'état réel de l'environnement
        root_loc = self.env.automata.currentLoc.copy()
        root_secr = self.env.automata.currentSecr.copy()
        root_cost = self.env.automata.currentCost
        
        # 2. Créer la racine de l'arbre
        root_node = MCTSNode(root_loc, root_secr, root_cost)
        
        # Initialiser les actions possibles depuis la racine
        self.env.resetState(root_loc, root_secr)
        self.env.automata.currentCost = root_cost
        root_node.untried_actions = self.env.automata.next(maxCost)
        
        if not root_node.untried_actions:
            return None # Deadlock
            
        # 3. Boucle principale du MCTS
        for i in range(self.num_iterations):
            node = root_node
            
            # --- Préparation : on remet l'environnement à l'état de la racine ---
            self.env.resetState(root_loc, root_secr)
            self.env.automata.currentCost = root_cost

            # --- PHASE 1 : SÉLECTION ---
            # On descend dans l'arbre avec UCT tant qu'on est sur des nœuds entièrement explorés
            while node.is_fully_expanded() and not self.env.done():
                node = self._select_best_child_uct(node)
                # On applique l'action dans l'environnement pour "avancer" mentalement
                self.env.automata.do(node.action)

            # --- PHASE 2 : EXPANSION ---
            # Si le nœud n'est pas final et a des actions non tentées
            if node.untried_actions and not self.env.done():
                # On choisit une action non tentée au hasard
                action = random.choice(node.untried_actions)
                node.untried_actions.remove(action)
                
                # On joue l'action dans l'environnement
                self.env.automata.do(action)
                
                # On crée le nouveau nœud enfant
                new_state_loc = self.env.automata.currentLoc.copy()
                new_state_secr = self.env.automata.currentSecr.copy()
                new_cost = self.env.automata.currentCost
                
                child_node = MCTSNode(new_state_loc, new_state_secr, new_cost, parent=node, action=action)
                # On récupère les actions possibles depuis ce nouvel enfant
                child_node.untried_actions = self.env.automata.next(maxCost)
                
                node.children.append(child_node)
                node = child_node # Le nœud courant devient l'enfant pour la simulation
                
            # --- PHASE 3 : SIMULATION ---
            # À partir du nouveau nœud, on joue au hasard jusqu'à la fin
            reward = self._simulate(maxCost)
            
            # --- PHASE 4 : RÉTROPROPAGATION ---
            # On remonte de la feuille jusqu'à la racine pour mettre à jour les stats
            self._backpropagate(node, reward)

        # 4. Restauration de l'état réel et choix final de l'action
        self.env.resetState(root_loc, root_secr)
        self.env.automata.currentCost = root_cost
        
        # On choisit l'enfant de la racine qui a été le plus visité (Robust Child)
        best_child = max(root_node.children, key=lambda c: c.visits)
        return best_child.action


    # --- Méthodes internes ---

    def _select_best_child_uct(self, node: MCTSNode) -> MCTSNode:
        # Formule UCT (Upper Confidence Bound applied to Trees)
        best_score = float('-inf')
        best_child = None
        
        for child in node.children:
            if child.visits == 0:
                # Si un enfant n'a jamais été visité, on lui donne une valeur infinie pour forcer l'exploration
                return child
            
            # Formule : Moyenne des scores + Constante * sqrt(ln(Visites Parent) / Visites Enfant)
            exploitation = child.score / child.visits
            exploration = self.exploration_constant * math.sqrt(math.log(node.visits) / child.visits)
            uct_value = exploitation + exploration
            
            if uct_value > best_score:
                best_score = uct_value
                best_child = child
                
        return best_child

    def _simulate(self, maxCost) -> float:
        # On joue des coups au hasard jusqu'à atteindre l'objectif, un deadlock, ou dépasser le coût max.
        current_step = 0
        # Limite arbitraire pour éviter les boucles infinies en simulation
        max_sim_steps = 20 
        
        while not self.env.done() and current_step < max_sim_steps:
            possible_actions = self.env.automata.next(maxCost)
            if not possible_actions:
                break # Deadlock
            
            # Choix aléatoire pur (Playout)
            action = random.choice(possible_actions)
            self.env.automata.do(action)
            current_step += 1
            
        # --- Fonction de Récompense (Très important pour le MCTS !) ---
        if self.env.done():
            # Si on a gagné, on donne un gros score. On peut pénaliser légèrement par le coût
            # pour encourager les attaques moins chères.
            # Ex: si maxCost = 300 et currentCost = 100, on gagne (300-100)/300 = 0.66
            return 1.0 + max(0, (maxCost - self.env.automata.currentCost) / maxCost)
        else:
            # Échec
            return 0.0

    def _backpropagate(self, node: MCTSNode, reward: float):
        # On remonte l'arbre jusqu'à la racine
        while node is not None:
            node.visits += 1
            node.score += reward
            node = node.parent