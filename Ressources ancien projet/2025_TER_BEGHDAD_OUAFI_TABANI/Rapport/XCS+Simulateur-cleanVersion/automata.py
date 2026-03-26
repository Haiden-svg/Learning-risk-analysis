from model import Model
from typing import List
from automaton import Location, Actions, Template, Trans, SetSecr, ActiveTransition
from UppaalTemplate import UppaalTemplate


# loop for all nodes
# memory of:
# - current states of nodes and secrets
# init: for all nodes:
# - template choice
# - all location to Location.FUNC
# - kwolegde of all secrets to False
# .....
# next:
# - list of all possible actions (transitions + secret modifications) for all nodes, with costs
#         actions : list of forced node locations, list of forced values (true/false) of secrets

# do:
# - execution of chosen actions


class Automata:
    model: Model
    # be carefull about the  currentLoc and currentSecr references, do not change them !!!
    currentLoc: List[Location]
    currentSecr: List[bool]
    nbNodes: int
    nbSecrets: int
    currentCost: int
    nodes: List[Template]
    nodeIndexByName: dict[str, int]
    secrIndexByname: dict[str, int]
    fallbackActions: List[Actions]

    def reset(self, currentLoc: List[Location], currentSecr: List[bool]):
        # to keep the same references of the lists 
        self.currentLoc.clear()
        for loc in currentLoc:
            self.currentLoc.append(loc)
        self.currentSecr.clear()
        for val in currentSecr:
            self.currentSecr.append(val)
        self.currentCost = 0

    def __init__(self, modelEnv: Model, currentLoc: List[Location], currentSecr: List[bool]):

        assert modelEnv is not None
        assert modelEnv.nodes is not None
        assert modelEnv.nbNodes is not None
        assert len(modelEnv.nodes) > 0
        self.nbNodes = modelEnv.nbNodes
        self.nbSecrets = modelEnv.nbSecrets
        self.model = modelEnv
        self.currentLoc = [loc for loc in currentLoc]
        self.currentSecr = [val for val in currentSecr]
        self.currentCost = 0
        self.nodes = []

        self.nodeIndexByName = {modelEnv.nodes[i].name: i for i in range(modelEnv.nbNodes)}
        self.secrIndexByname = {modelEnv.secrets[i]: i for i in range(modelEnv.nbSecrets)}

        # fallback action list for the entire system 
        self.fallbackActions = []

        for i in range(len(modelEnv.fallbackActions)):
            act = Actions()
            s = modelEnv.fallbackActions[i].value.split(';')
            for l in range(len(s)):
                if s[l].startswith("status["):
                    nstart = s[l].index("[") + 1
                    nstop = s[l].index("]")
                    nodeInd = int(s[l][nstart:nstop])
                    if s[l][nstop + 2:nstop + 3] == "F":
                        loc = Location.FUNC
                    elif s[l][nstop + 2:nstop + 3] == "B":
                        loc = Location.BADD
                    elif s[l][nstop + 2:nstop + 3] == "N":
                        loc = Location.NOAV
                    else:
                        loc = None
                    if loc is not None:
                        trans = Trans(nodeInd, loc)
                        act.transitions.append(trans)
                elif s[l].startswith("secrStolen["):
                    nstart = s[l].index("[") + 1
                    nstop = s[l].index("]")
                    secrInd = int(s[l][nstart:nstop])
                    if s[l][nstop + 2:nstop + 3] == "f":
                        valB = False
                    elif s[l][nstop + 2:nstop + 3] == "t":
                        valB = True
                    else:
                        valB = None
                    if valB is not None:
                        setSecr: SetSecr = SetSecr(secrInd, valB)
                        act.secretChange.append(setSecr)
            if len(act.secretChange) > 0 or len(act.transitions) > 0:
                self.fallbackActions.append(act)

        # simplified version : only one automaton template !!!!
        globalTranIndex: int = 0
        autom: Template
        for i in range(modelEnv.nbNodes):
            if modelEnv.nodes[i].softwareClass != "unknown":
                self.nodes.append(
                    autom := UppaalTemplate(modelEnv, i, self.currentLoc, self.currentSecr, self.nodeIndexByName,
                                            self.secrIndexByname, self.fallbackActions, globalTranIndex)
                )
                globalTranIndex += sum([len(autom.automaton[loc]) for loc in autom.automaton])
                assert (len(autom.automaton) == 0 or (globalTranIndex - 1) == max(
                    [trans.transIndex for loc in autom.automaton for trans in autom.automaton[loc]]))
            else:
                raise Exception("Sorry, unknown software claass")

    def next(self, maxCost: int) -> List[ActiveTransition]:
        transitionList: List[ActiveTransition] = []
        for i in range(self.nbNodes):
            transitionList.extend(self.nodes[i].next(maxCost, self.currentCost))
        #print(f"[DEBUG] Transition totale disponible : {len(transitionList)} avec currentCost={self.currentCost}")
        return transitionList

    # returns number of lactions en secrets modified
    def do(self, transition: ActiveTransition) -> int:
        assert transition is not None
        # update locations, secrets and current cumulated cost
        self.currentCost += transition.cost
        #print(f"[DO] Nouvelle transition appliquée, coût total = {self.currentCost}")
        nn = 0
        for soft in transition.update.transitions:
            self.currentLoc[soft.softComp] = soft.location
            nn += 1
        for secr in transition.update.secretChange:
            self.currentSecr[secr.secr] = secr.val
            nn += 1

        return nn  # number of modified locations and secrets
