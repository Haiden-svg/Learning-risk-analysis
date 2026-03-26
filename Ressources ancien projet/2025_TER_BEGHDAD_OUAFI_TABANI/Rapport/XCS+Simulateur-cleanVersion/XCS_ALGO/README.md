Pour charger le model souhaité il suffit de modifier la ligne 18 dans le fichier initialisation.py :  
`systemPath = "../jsons/ResilientCarMonv5.json"  # spécifier le model à utiliser`


un fichier "nomDuModel.start" doit etre existant dans le dossier jsonavant d'initialiser le simulateur (le simulateur
demande un fichier pour les états initiaux) ce fichier n'est pas exigé dans l'algorithme car on spécifie nous meme les
états cibles et donc ce n'est pas grave si le simulateur à comme cible un SEUL module la ou l'algo peut avoir plusieurs


Dans l'état actuel on peut donner une liste d'une ou plusieurs cibles lors de l'initialisation, ligne 51 dans initialisation.py :  
`TARGET_INDEX_resilientcar_model = [automata.nodeIndexByName["AdasDec"], automata.nodeIndexByName["BreakCtrl"], automata.nodeIndexByName["EngActu"], automata.nodeIndexByName["PwTrain"]]`

L'état cible n'est pas important dans cette version du code, l'algorithme verifie uniquement si le module a un état
différent de FUNC pour la simplicité  
Pour modifier cela il suffit de modifier la ligne 129 dans le fichier XCS_running.py :  
`if self.automata.currentLoc[target] != Location.FUNC:  # mettre == self.target_state si on veut spécifier un état précis de la cible`

Si le changement est effecuté l'état cible sera BADD peu importe quel module cible est choisi (ceci aussi peut etre modifié
en modifiant la ligne 55 dans initialisation.py :
`variable TARGET_STATE = Location.BADD`


Résumé du fonctionnement de l'algorithme xcs (propre à cette librairie)  
au lancement :  
    - Appel de la fonction reset qui met toutes les varibales à l'etat initial (valeur NULL)  
    - Appel de la fonction `get_all_transitions()` dans le constructeur pour récupérer toutes les transitions du model  
    - Appel de la fonction `initialize_action_encodings()` pour encoder les transitions dans un format précis
                                (ceci est nécessaire car les transitions récupérées depuis le model et les transitions
                                 récupérées depuis l'automate pendant la boucle sont des objets différents)  
    - Appel de la fonction `get_possible_actions()` qui renvoie tout les id de toutes les transitions
                                (lalgo ne mets jamais à jour la table des id des transitions d'ou l'importance de tout
                                lui donner dés le debut)  

Pendant la boucle d'apprentissage:  
    - Appel de la fonction `more()`  
    - Appel de la fonction `execute()` avec un id de transition choisie par l'algo lui meme (répétée jusqu'a avoir une transition valide)  
    - Appel de la fonction `sense()` pour récupérer l'état du système  

Le défaut de cette librairie est la lenteur lors des choix des id de transitions, exemple:
    si on se trouve dans un état du système ou seule la transition N°45 est valide, l'algo doit la trouver parmis
    395 transitions pour le model complet, car cette bibliothèque ne permet pas un changement dynamique de la table
    ou il pioche ces ids
    
L'une des amélioration possible c'est de modifier cette bibliothèque ou d'utiliser une autre qui permet de lui
spécifier nous meme les transitions valide, de cette manière on peut pénaliser toutes les autres transtions
d'un coup et le laisser choisir plus facilement dans les restantes, ça évitra de de longues boucle for pour chercher une
transitions parmis des centaines


