import pickle
from collections import Counter

from xcs import XCSAlgorithm
from xcs.framework import EpsilonGreedySelectionStrategy

from XCS_running import CarHackScenario

from automaton import Location
from model import Model
from automata import Automata
from batchInit import InitBatch
import json


def initialize_simulator():
    systemPath = "../jsons/ResilientCarMonv5.json"  # spécifier le model à utiliser
    with open(systemPath, "r") as JsonFile:
        data = json.load(JsonFile)
    model = Model(**data)

    batchFilePath = systemPath.replace(".json", ".start")
    with open(batchFilePath, "r") as JsonFile:
        data_init = json.load(JsonFile)
    # Boucle sur les états initiaux
    init_nodes = {}
    for state in data_init["init"]["states"]:
        init_nodes[state['softComp']] = state['location']

    initBatch = InitBatch(batchFilePath, model)
    initialLoc = initBatch.initialLoc
    initialtSecr = initBatch.initialtSecr
    netAutomata = Automata(model, initialLoc, initialtSecr)
    return model, netAutomata, initialLoc, initialtSecr, init_nodes


# === Initialiser le simulateur ===
vehicle_model, automata, init_loc, init_secr, initNodes = initialize_simulator()

# === Paramètres ===
TARGET_INDEX_resilientcar_model = [automata.nodeIndexByName["AdasDec"], automata.nodeIndexByName["BreakCtrl"],
                                   automata.nodeIndexByName["EngActu"], automata.nodeIndexByName["PwTrain"]]

#TARGET_INDEX_medium_model = [automata.nodeIndexByName["ExBrowser"]]
TARGET_STATE = Location.BADD
MAX_COST = 95
XCS_ITERATIONS = 1000
MAX_EPISODE_STEPS = 5

# === Créer le scénario XCS ===
scenario = CarHackScenario(automata, init_loc, init_secr, TARGET_INDEX_resilientcar_model, TARGET_STATE, MAX_COST, MAX_EPISODE_STEPS)

# === Lancer l'entraînement XCS ===
algorithm = XCSAlgorithm()

algorithm.exploration_probability = 0.55
algorithm.exploration_strategy = EpsilonGreedySelectionStrategy(0.55)
algorithm.discount_factor = 1
algorithm.do_ga_subsumption = True
algorithm.do_action_set_subsumption = True

xcs_model = algorithm.new_model(scenario)

print("\n Démarrage de l'apprentissage XCS...")
for i in range(0, XCS_ITERATIONS):
    print(f"itération: {i}/{XCS_ITERATIONS}")
    scenario.reset()
    xcs_model.run(scenario, learn=True)

print(f"\n Apprentissage terminé après {XCS_ITERATIONS} itérations.")

sorted_rules = sorted(xcs_model, key=lambda rule: rule.fitness, reverse=True)
print("\n=== Toutes les règles apprises par XCS ===")
for i, rule in enumerate(sorted_rules):
    print(f"Règle {i}:")
    print(f"  Condition        : {rule.condition}")
    print(f"  Action ID        : {rule.action}")
    print(f"  Prédiction       : {rule.prediction:.2f}")
    print(f"  Erreur           : {rule.error:.2f}")
    print(f"  Fitness          : {rule.fitness:.2f}")
    print(f"  Expérience       : {rule.experience}")
    print(f"  Timestamp        : {rule.time_stamp}")
    print(f"  Action Set Size  : {rule.action_set_size:.2f}")
    print(f"  Numerosity       : {rule.numerosity}")
    print("--------------------------------------------------")

# === TESTING ===
print("\nPhase de test XCS (sans apprentissage)...")
TEST_EPISODES = 50
successes = 0

for ep in range(1, TEST_EPISODES + 1):
    print(f"\nTest épisode {ep}/{TEST_EPISODES}")
    scenario.reset()

    xcs_model.run(scenario, learn=False)

    # print("Chemin exécuté :")
    for i, tr in enumerate(scenario.trace):
        print(f"Étape {i + 1}: {tr.name} → coût: {tr.cost}")

    for target in scenario.target_index:
        if scenario.automata.currentLoc[target] != Location.FUNC:  # mettre == self.target_state si on veut spécifier un état précis de la cible
            successes += 1
            break

print(f"\nTaux de réussite : {successes}/{TEST_EPISODES} épisodes ({(successes / TEST_EPISODES) * 100:.1f}%)\n")

position_counter = Counter()

for rule in xcs_model:
    action_id = rule.action
    transition = scenario.action_decoder.get(action_id)
    if not transition or not transition.update.transitions:
        continue

    target_node = transition.update.transitions[0].softComp
    target_loc = transition.update.transitions[0].location

    # Balaye toutes les entrées possibles vers ce noeud
    for input_entry in scenario.automata.model.nodes[target_node].inputs:
        position = input_entry.position
        position_counter[position] += rule.numerosity
        break

# Résultat
print("Positions d’attaque préférées (pondérées par la numerosity des règles) :")
for pos, count in position_counter.most_common():
    print(f"{pos}: {count}")

# Sauvegarde le model entrainé
with open("xcs_model1.pkl", "wb") as f:
    pickle.dump(xcs_model, f)
