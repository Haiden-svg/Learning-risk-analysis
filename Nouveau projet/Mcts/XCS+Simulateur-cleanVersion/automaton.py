from typing import List, Callable, Optional
from abc import ABC
from model import Model, Node
from enum import Enum
from dataclasses import dataclass


class Location(Enum):
    FUNC = 0
    MALW = 1
    BADD = 2
    NOAV = 3


@dataclass
class Trans:
    softComp: int
    location: Location


@dataclass
class SetSecr:
    secr: int
    val: bool


class Actions:
    transitions: List[Trans]
    secretChange: List[SetSecr]

    def __init__(self):
        self.transitions = []
        self.secretChange = []


@dataclass
class Transition:
    name: str
    guard: Callable[
        [], int]  # entry prameter :  context parameter (here:node index) return value = costs (>=0 transition can fire)
    update: Actions
    transIndex: int  # index within the entire system transitions


@dataclass
class ActiveTransition:
    name: str
    model: Model
    nodeIndex: int
    cost: int
    update: Actions
    nodeLocation: Location
    transIndex: int  # index of transition in the location

    def __str__(self):
        s: str = ""
        if self.nodeIndex >= 0:
            nodeName = self.model.nodes[self.nodeIndex].name
            s = f"Node:{nodeName}°{self.nodeIndex} {self.nodeLocation} Transition:{self.name}, cost:{self.cost} Actions: "
        else:
            s = f"{self.name}\n\t Actions:"  # for artificial transitions
        for act in self.update.transitions:
            nName: str = self.model.nodes[act.softComp].name
            s = s + f" {act.location} => node:{nName}°{act.softComp} | "
        # s=s+"\t\n"
        for act in self.update.secretChange:
            sName: str = self.model.secrets[act.secr]
            s = s + f" {act.val} => secret:{sName}°{act.secr} | "
        # s=s+"\t\n"
        return s


class Template(ABC):
    model: Model
    node: Node
    nodeIndex: int
    currentLoc: List[Location]
    currentSecr: List[bool]
    isOpenL: List

    statCoding: dict[str, str]
    nodeIndexByName: dict[str, int]
    secrIndexByname: dict[str, int]

    automaton: dict[Location, List[Transition]]

    fallbackActions: Optional[List[Actions]] = None

    # list of fallback and steal secret actions
    toMfallbackActInd: Optional[int] = None
    toBfallbackActInd: Optional[int] = None
    toNfallbackActInd: Optional[int] = None

    def ScoreExprToPython(self, entry: str, sourceNodeIndex: int) -> str:
        s: List[str] = entry.split(" ")
        pythonstr: str = ""
        for i in range(len(s)):
            if len(s[i]) == 0:
                pythonstr += " "
            elif s[i] == "=":
                pythonstr += " == "
            elif s[i] == "<>":
                pythonstr += " != "
            elif s[i] == "|":
                pythonstr += " or "
            elif s[i] == "&":
                pythonstr += " and "
            elif s[i].startswith("$"):
                pythonstr += self.statCoding.get(s[i], s[i])
            elif s[i].startswith("key("):
                list: str = s[i][4: s[i].index(")")]
                secrets: List[str] = list.split(":")
                if len(secrets) < 2:
                    pythonstr += "self.key(" + str(sourceNodeIndex) + "," + secrets[0] + ")"
                else:
                    pythonstr += "("
                    for k in range(len(secrets)):
                        if k > 0:
                            pythonstr += "  or "
                        pythonstr += (
                                "self.key(" + str(sourceNodeIndex) + "," + secrets[k] + ")"
                        )
                    pythonstr += ")"
            elif s[i][0:1].isalpha():
                pythonstr += (
                        "self.currentLoc[" + str(self.nodeIndexByName.get(s[i])) + "]"
                )
            elif s[i][0:1] == "#":
                pythonstr += "True" if (s[i][1:2] == "t" or s[i][1:2] == "T") else "False"
            else:
                pythonstr += " " + s[i]
        return pythonstr

    def __init__(
            self,
            modelEnv: Model,
            nodeIndex: int,
            currentLoc: List[Location],
            currentSecr: List[bool],
            nodeIndexByName: dict[str, int],
            secrIndexByname: dict[str, int],
            fallbackActions: List[Actions],
            transIndex: int
    ):
        self.model = modelEnv
        self.node = modelEnv.nodes[nodeIndex]
        self.nodeIndex = nodeIndex
        self.fallbackActions = fallbackActions
        # be carefull about the  currentLoc and currentSecr references, do not change them !!!
        self.currentLoc = currentLoc
        self.currentSecr = currentSecr

        self.statCoding = {  # for compatibility with CTIRA 
            "$F": "Location." + Location._member_names_[0],
            "$M": "Location." + Location._member_names_[1],
            "$B": "Location." + Location._member_names_[2],
            "$N": "Location." + Location._member_names_[3]
        }

        self.nodeIndexByName = nodeIndexByName
        self.secrIndexByname = secrIndexByname
        self.isOpenL = []
        self.automaton = {}

        # creation of action patterns for fallbacks, costs set to 0 

        self.toMfallbackActInd = modelEnv.nodes[nodeIndex].fallbackActionIndex.toM
        self.toBfallbackActInd = modelEnv.nodes[nodeIndex].fallbackActionIndex.toB
        self.toNfallbackActInd = modelEnv.nodes[nodeIndex].fallbackActionIndex.toN

        # input generation of isOpen() table  for all component inputs !!!
        if self.node.nbInputs is None:
            return
        if self.node.nbInputs <= 0:
            return
        for k in range(len(self.node.inputs)):
            scope = {}  # Créer un dictionnaire pour capturer les fonctions définies par exec()
            globalEnv = {"Location": Location}

            exprs: str = self.ScoreExprToPython(  # CTI-RA to Python
                self.node.inputs[k].isOpen, self.node.inputs[k].sourceNodeIndex
            )
            code_str: str = "\ndef isOpen(self)->bool:\n\t return(" + exprs + ")\n"
            # Utilisation de exec() pour créer une fonction à partir de la chaîne
            exec(code_str, globalEnv, scope)

            f = scope["isOpen"]
            self.isOpenL.append(f.__get__(self,
                                          Template))  # Rendre la fonction disponible dans la liste isOpenL, dans l'instance node, avec l'accès à self

    # list of possible transitions
    def next(self, maxCost: int, currentCost: int) -> List[ActiveTransition]:
        # loop for all transitions !!!!!!
        location: Location = self.currentLoc[self.nodeIndex]
        transL: list[Transition]
        trans: Transition
        firedL: List[ActiveTransition] = []
        if location in self.automaton:
            transL = self.automaton[location]
            for trans in transL:  # all transitions per locality
                k: int = trans.guard()
                ind: int = trans.transIndex  # index within the entire system transitions
                if k >= 0 and k + currentCost <= maxCost:
                    firedL.append(
                        ActiveTransition(trans.name, self.model, self.nodeIndex, k, trans.update, location, ind))
        return firedL

    def key(self, nodeIndex: int, secrId: int) -> bool:
        ret: bool = self.currentSecr[secrId] or self.model.nodes[nodeIndex].secrStore[secrId]
        k: Optional[int] = None
        k = self.model.nodes[nodeIndex].kernelIndex
        if (k is not None):
            ret = ret or self.model.nodes[k].secrStore[secrId]
        return ret
