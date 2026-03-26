from __future__ import annotations
from typing import List,Optional
from automaton import Location, Actions, Trans, SetSecr
import sys
import os
import json
from model import Model

from typing import List, Optional

from pydantic import BaseModel


class JTrans(BaseModel):
    softComp: str
    location: str


class JSetSecr(BaseModel):
    secr: str
    val: bool

class SetStates(BaseModel):
    states: Optional[List[JTrans]] = None
    secrets: Optional[List[JSetSecr]] = None

class InitFinal(BaseModel):
    init: SetStates
    final:SetStates

class InitBatch ():
    initialLoc:List[Location]
    initialtSecr:List[bool]
    finalState:Actions
    cr:int
    model:Model

    def __init__(self,path:str, system: Model) :

        self.system=system

        # name to index for nodes and secrets
        nodeIndexByName = {system.nodes[i].name : i for i in range(system.nbNodes)} 
        secrIndexByname = {system.secrets[i] : i for i in range(system.nbSecrets)} 

        if path is None:
            self.cr=-1
            return
        if not os.path.exists(path):
            self.cr=-2
            return  None
        #json file parsing 
        with open(path, "r") as JsonFile:
            data = json.load(JsonFile)
        initFinal = InitFinal(**data)


        # start state initialisation
        self.initialLoc = [Location.FUNC for i in range(system.nbNodes)]
        self.initialtSecr = [False for i in range(system.nbSecrets)]
        if initFinal.init.states is None:
            self.cr=-3
            return 
        for jTrans in initFinal.init.states:
            self.initialLoc[nodeIndexByName[jTrans.softComp]]=Location[jTrans.location]
        if initFinal.init.secrets is not None:
            for jSetSecr in  initFinal.init.secrets:
                self.initialtSecr[secrIndexByname[jSetSecr.secr]]= jSetSecr.val


        # Final state initialisation
        if initFinal.final.states is  None and  initFinal.final.secrets is None:
            self.cr=-4
            return
        self.finalState=Actions()
        if initFinal.final.states is not None:
            self.finalState.transitions= [ Trans(nodeIndexByName[jTrans.softComp], Location[jTrans.location]) for jTrans in initFinal.final.states ]
        if initFinal.final.secrets is not None:
            self.finalState.secretChange=[ SetSecr(secrIndexByname[jSetSecr.secr], jSetSecr.val) for jSetSecr in  initFinal.final.secrets ]
        self.cr=0
        return

    def __str__(self):
        s="\nInitialization : "  
        k=0
        for i in range(self.system.nbNodes):
            if self.initialLoc!=Location.FUNC:
                name:str=self.system.nodes[i].name
                if k>0: s=s+" => "
                else:k=1
                s=s+f" node:{self.system.nodes[i].name}: {self.initialLoc[i].name}"
        k=0
        for i in range(self.system.nbSecrets):
            if self.initialtSecr[i]:
                if k==0: s=s+"Secrets to True: "
                if k>0: s=s+" & "
                else:k=1
                s=s+f"{self.system.secrets[i]}"

        s=s+"\nTarget : "  
        k=0

        if self.finalState.transitions is not None:
            for act in self.finalState.transitions:
                nName:str=self.system.nodes[act.softComp].name 
                if k>0: s=s+" & "
                else:k=1
                s=s+f"{act.location} for node:{nName}°{act.softComp}"
        if self.finalState.secretChange is not None:
            k=0
            s=s+" & "
            for act in self.finalState.secretChange:
                sName:str=self.system.secrets[act.secr] 
                if k>0: s=s+" & "
                else:k=1
                s=s+f"{act.val} for secret:{sName}°{act.secr}"
        s=s+"\n"  
        return s

