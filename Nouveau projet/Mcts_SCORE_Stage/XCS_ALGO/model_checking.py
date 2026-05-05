import pickle


with open("xcs_model1.pkl", "rb") as f:
    model = pickle.load(f)

sorted_rules = sorted(model, key=lambda r: (r.fitness, r.prediction), reverse=True)
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
    print("------------------------------------------------------")



