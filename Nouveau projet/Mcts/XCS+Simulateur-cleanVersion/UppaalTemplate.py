from model import Model
from typing import List,Optional
from automaton import Actions, Trans, Location, Template, Transition,SetSecr


class UppaalTemplate(Template):

    def ProtDestructCost(self,inpId:int,roleIndex:int,sourceNodeIndex:int,attack_position:str,attackerState:Location)->int :
        protBreakable:bool=True
        tunBreakable:bool=True
        tunnelOn:bool=self.node.inputs[inpId].protBreakCosts.tunnelProtocol is not None and attack_position!="peer" # no tunnel to break for the peer position !!! 

        if attackerState==Location.FUNC:
            return -1
        if (attackerState==Location.NOAV or not self.isOpenL[inpId]()) and attack_position=="peer":
            return 0
        if attackerState!=Location.MALW and attack_position!="peer":
            return -1        
        if self.node.inputs[inpId].protBreakCosts.destruct is None and self.node.inputs[inpId].protBreakCosts.theft is None:
            protBreakable=False
        if tunnelOn and self.node.inputs[inpId].protBreakCosts.tunnelDecrypt is None and self.node.inputs[inpId].protBreakCosts.tunnelDestroy is None:
            tunBreakable=False
        destruct:int=-1
        if self.node.inputs[inpId].protBreakCosts.destruct is not None:
            destruct=self.node.inputs[inpId].protBreakCosts.destruct
        tunnelDestroy:int=-1
        tunnelDecrypt:int=-1
        if self.node.inputs[inpId].protBreakCosts.tunnelDestroy is not None:
            tunnelDestroy=self.node.inputs[inpId].protBreakCosts.tunnelDestroy
        if self.node.inputs[inpId].protBreakCosts.tunnelDecrypt is not None:
            tunnelDecrypt=self.node.inputs[inpId].protBreakCosts.tunnelDecrypt
        kernelIndex:int=-1
        if self.model.nodes[sourceNodeIndex].kernelIndex is not None:
            kernelIndex=self.model.nodes[sourceNodeIndex].kernelIndex

        if (tunnelOn and not tunBreakable) and not protBreakable :
            return -1

        costDestroy:int=-1  # cost of session destruction
        if tunnelOn : # today no key to protect tunnels  
            if tunnelDecrypt>=0 and destruct>=0:
                costDestroy=tunnelDecrypt+destruct
            if tunnelDestroy>=0:
                if costDestroy>=0:
                    if tunnelDestroy>costDestroy:
                        costDestroy=tunnelDestroy
                else:
                    costDestroy=tunnelDestroy
        else:
            costDestroy=destruct
 
        #  normally it is easier to put down than enter a protocol, but we consider also the contray case
        if self.node.inputs[inpId].protBreakCosts.theft is None or (tunnelDecrypt<0 and tunnelOn):
            return costDestroy
        theft:int=self.node.inputs[inpId].protBreakCosts.theft
        for i in range(self.model.nbSecrets):
            if self.node.roles[roleIndex].sessionProtectSecretIndex[i]:
                kerSt:bool=False
                if kernelIndex >=0:
                    kerSt=self.model.nodes[kernelIndex].secrStore[i]
                if kerSt or self.node.secrStore[i] or self.currentSecr[i] :
                    theft=0   # application protocol is set to zero if one of the protection secret is available

        costInjData:int=-1
        if tunnelOn:   # no key for tunnel protection !!!!! 
            costInjData= tunnelDecrypt + theft
        else:
            costInjData= theft

        if costDestroy<0:
            return costInjData
        if costInjData<0 or costDestroy<costInjData:
            return costDestroy
        return costInjData

    def minNonDispCost(self) -> int : # returns the sum of costs for all inputs able to produce Non availability state (sN), -1 if impossible 

        # "N" malware installation is not considered here  

        rolCostNonAvail:List[int] = self.node.nbRoles*[-1]
        rolOk:List[bool] = self.node.nbRoles*[True]  #  true if a role can stay OK thanks to legitimate producers, "no system roles only" are considered
        for i in range(self.node.nbInputs):
            rolOk[self.node.inputs[i].roleIndex]=False
        nbOKnMand:int=0
        tcost:int=-1 # tcost  min cost of manadatory role compromission 

        # for all "no system" inputs: we memorise potentiel B et M available attacker nodes and costs of protocol  destruction 
        for i in range(self.node.nbInputs):
            assert self.node.roles[self.node.inputs[i].roleIndex].type is not None and self.node.roles[self.node.inputs[i].roleIndex].categ is not None
            roleType:str=self.node.roles[self.node.inputs[i].roleIndex].type
            roleCateg:str=self.node.roles[self.node.inputs[i].roleIndex].categ
            roleIndex:int=self.node.inputs[i].roleIndex
            sourceNodeIndex:int=self.node.inputs[i].sourceNodeIndex 
            if self.isOpenL[i]() and roleType!="system" and roleCateg!="transparent": #  reachable  and important and no system role 
                attackerState:Location=self.currentLoc[sourceNodeIndex]
                attack_position=self.node.inputs[i].position
                sessDestruct:int=-1
                if (attackerState==Location.FUNC) and (attack_position=="peer") and self.isOpenL[i]() :
                    rolOk[roleIndex]=True
                if (rolCostNonAvail[roleIndex]!=0): 
                    sessDestruct=self.ProtDestructCost(i,roleIndex,sourceNodeIndex,attack_position,attackerState)
                    if (sessDestruct >=0):
                        if (rolCostNonAvail[roleIndex] < 0):
                            rolCostNonAvail[roleIndex]=sessDestruct
                        elif (sessDestruct < rolCostNonAvail[roleIndex]):
                            rolCostNonAvail[roleIndex]=sessDestruct

        #  min cost of mandatory roles compromissions and count of compromisable OK roles
        for role in range(self.node.nbRoles):
            roleType:str=self.node.roles[role].type
            roleCateg:str=self.node.roles[role].categ
            if roleType!="system" and roleCateg!="transparent" : # //no system and no tranparent roles
                if roleCateg=="mandatory" : #  mandatory role  
                    if not rolOk[role]:
                        return 0 # peer Position  not available or in non F state
                    if rolCostNonAvail[role]>=0 :
                        if (tcost<0) or (rolCostNonAvail[role]<tcost):
                            tcost=rolCostNonAvail[role]  # minimal cost of  the compromissions of the mandatory role => tcost         
                elif (roleCateg=="optional"):
                    if (rolOk[role]):
                        nbOKnMand+=1          

        actThreshold:int=0
        if self.node.actThreshold is not None:
            actThreshold=self.node.actThreshold
    
        if ( nbOKnMand < actThreshold ):
            return 0 #  not enough of non mandatory roles are active

        assert actThreshold>=0

        if actThreshold ==0:
            return tcost # activity threshold not defined

        nbtocomp:int=1+nbOKnMand-actThreshold  # number of optional role necessary to compromise
        if nbtocomp <= 0:
            return 0 # non enough optional actives roles

        bdCost:int=-1 #   min cost of optional role compromissionq 
        tr:int=0 # number of alreday chosen optional role to be compromised 
        # minimal cost of the non mandatory roles' compromissions
        for k in range(self.node.nbRoles):
          tr1:int=-1  # temporary cost for optimal choice
          j:int=-1 # selected role
          # choice of a role with the minimal cost not alreday selected
          for role in range(self.node.nbRoles):
            roleType:str=self.node.roles[role].type
            roleCateg:str=self.node.roles[role].categ
            if ( roleType!="system" and roleCateg=="optional" and (rolCostNonAvail[role] >=0) and (tr<nbtocomp) ) :#  //only non mandatory roles not already selected
                if ( (tr1<0) or (tr1>rolCostNonAvail[role]) ) :
                    tr1=rolCostNonAvail[role]
                    j=role #  role of min cost
          if (j>=0):  
            tr+=1
            rolCostNonAvail[j]=-1
            if bdCost<0:
                bdCost=tr1
            else:
                bdCost+=tr1
        if tr<nbtocomp or (tcost > 0 and tcost<bdCost):
            return tcost # cost of mandatory role compromission  
        return bdCost # cost of optional role compromissions 

    def ProtProtectCost(self,inpId:int, roleId:int, sourceNodeIndex:int,attack_position:str) -> int: # // cost of protocol session theft

        assert self.currentLoc[sourceNodeIndex] == Location.MALW or (attack_position=="peer" and self.currentLoc[sourceNodeIndex]==Location.BADD)
          
        if self.node.inputs[inpId].protBreakCosts.theft is None:
            return -1
        
        theft:Optional[int]=self.node.inputs[inpId].protBreakCosts.theft
        if theft is None:
            return -1
        tunnelDecrypt:Optional[int]=self.node.inputs[inpId].protBreakCosts.tunnelDecrypt 
        kernelSId:Optional[int]=self.model.nodes[sourceNodeIndex].kernelIndex 
        keyPossess:bool=False
        keyRole:bool=False
        if self.model.nbSecrets is not None : # verification of the possession of role session protections keys 
            for i in range(self.model.nbSecrets):
                if self.node.roles[roleId].sessionProtectSecretIndex[i] : 
                    keyRole=True
                    if kernelSId is not None:
                        keyPossess = keyPossess or self.model.nodes[kernelSId].secrStore[i] 
                    keyPossess=self.currentSecr[i] or self.model.nodes[sourceNodeIndex].secrStore[i] 
        #  application protocol is set to zero if one of the protection secret is available
        if attack_position=="peer": # special case for the "peer" position, only application protocol is to consider
            if (keyRole and not keyPossess):
                if self.currentLoc[sourceNodeIndex]==Location.BADD:
                    return -1 # bad data is not able to break 
                return theft
            else:
                return 0
        if tunnelDecrypt is None:
            return theft
        elif tunnelDecrypt>0 :
            return theft+tunnelDecrypt
        return theft




    def minBadDataCost(self) ->int:#  returns the sum of costs for all inputs capable of producing bad data, -1 if impossible 
         # "B" malware installation is not considered here 
        rolCostBd:List[int] = self.node.nbRoles*[-1]
        rolOk:List[bool] = self.node.nbRoles*[True]  #  true if a role can stay OK thanks to legitimate producers, "no system roles only" are considered
        for i in range(self.node.nbInputs):
            rolOk[self.node.inputs[i].roleIndex]=False
        # for all no system inputs: we memorise potentiel B et M available attacker nodes and costs of B data submissions, B cost in composed from two values, session breaking and acceptable bad data generation, sum of Ok Weight 
       #  first round, minimal costs  for available partners 
        # for all "no system" inputs: we memorise potentiel B et M available attacker nodes and costs of protocol  destruction 
        for i in range(self.node.nbInputs):
            assert self.node.roles[self.node.inputs[i].roleIndex].type is not None and self.node.roles[self.node.inputs[i].roleIndex].categ is not None
            roleType:str=self.node.roles[self.node.inputs[i].roleIndex].type
            roleCateg:str=self.node.roles[self.node.inputs[i].roleIndex].categ
            roleIndex=self.node.inputs[i].roleIndex
            sourceNodeIndex=self.node.inputs[i].sourceNodeIndex
            if self.isOpenL[i]() and roleType!="system" and roleCateg!="transparent": #  reachable  and no trasparent and no system role 
                attackerState:Location=self.currentLoc[sourceNodeIndex]
                attack_position=self.node.inputs[i].position
                dataBreakCost:Optional[int] = None
                dataBreakCost=self.node.roles[roleIndex].dataBreakCost
                if (attackerState==Location.FUNC) and (attack_position=="peer") and self.isOpenL[i]() :
                    rolOk[roleIndex]=True
                if (
                    rolCostBd[roleIndex]!=0 and dataBreakCost is not None and ( attackerState == Location.MALW or 
                                                                               (attackerState==Location.BADD and attack_position=="peer")
                                                                               )
                    ):
                    sessTheft:int=self.ProtProtectCost(i,roleIndex,sourceNodeIndex,attack_position)
                    if (sessTheft >=0):
                        assert dataBreakCost>=0
                        sessTheft+=dataBreakCost
                        if (rolCostBd[roleIndex] < 0):
                            rolCostBd[roleIndex]=sessTheft
                        elif (sessTheft < rolCostBd[roleIndex]):
                            rolCostBd[roleIndex]=sessTheft

 
        # number of roles OK and potentially compromisable, compliance with mandatory roles
        mustcopromise:int=-1 # cost of compromission (with bad data injection) of all manadatrory and not OK roles, to preserve the node activity
        tcost:int=-1 # min cost of manadatory role compromission             
        totRolOK:int=0 # number of active optionnal roles
        for role in range(self.node.nbRoles):
            roleType:str=self.node.roles[role].type
            roleCateg:str=self.node.roles[role].categ
            tcost:int=-1   # minimal cost of  the compromissions of one of the mandatory roles
            if roleType!="system" and roleCateg!="transparent": # no system roles , no trasparent role
                if roleCateg=="mandatory" :
                    if rolCostBd[role]<0 and not rolOk[role]:
                        return -1 #  impossible to inject bad dat to not active mandatory role
                    if not rolOk[role]:
                        if mustcopromise>0:
                            mustcopromise+=rolCostBd[role]
                        else :
                            mustcopromise=rolCostBd[role]# cost of compromission of all manadatrory and not OK roles, to preserve activity
                    if rolCostBd[role] >=0 and (tcost<0 or rolCostBd[role]<tcost): # roel mus be corpomissable 
                        assert rolCostBd[role] >=0
                        tcost=rolCostBd[role] #   minimal cost of  the compromissions of one of the mandatory role => tcost 
                elif rolOk[role]:
                    assert roleCateg=="optional"
                    totRolOK+=1  #  number of OK optionnal roles

        if self.node.actThreshold is None:
            actThreshold=0
        else:
            actThreshold=self.node.actThreshold
        if mustcopromise >0  and totRolOK >=actThreshold:
            return mustcopromise 
        
        # adding necessary non active optional roles for minimal activity
        nbCompr:int =actThreshold - totRolOK
        activityCost:int=0
        totRolBd:int=0
        for k in range(self.node.nbRoles):
            if (nbCompr>0):
                tr1:int=-1
                j:int=0
                for role in range(self.node.nbRoles):
                    if self.node.roles[role].type!="system" and self.node.roles[role].categ=="optional" and rolCostBd[role] > 0 and not rolOk[role] :#  only optional, no system roles
                        if tr1<0 or tr1>rolCostBd[role]:
                            tr1=rolCostBd[role]
                            j=role # role of min cost
                if tr1>=0:
                    nbCompr-=1
                    totRolBd+=1
                    activityCost += tr1
                    rolCostBd[j]=-1
                    totRolOK+=1 
        if nbCompr>0:
            return -1 # impossible to have enough active optional roles

        if mustcopromise>=0:
            return activityCost + mustcopromise #  no necessary to add supplementary optionnal role to achieve plausThreshold

        # adding necessary active optional roles for input bad data
        if self.node.plausThreshold is None:
            plausThreshold=1
        else:
            plausThreshold=self.node.plausThreshold
        nbCompr =plausThreshold - totRolBd #  totRolBd === already compromised optional roles to maintain activity
        bdCost=-1
        for k in range(self.node.nbRoles):
            if nbCompr>0 : # for OK role only
                tr1:int=-1
                j:int=-1
                for role in range(self.node.nbRoles):
                    if self.node.roles[role].type!="system" and self.node.roles[role].categ=="optional" and rolCostBd[role] >=0 and rolOk[role] : # only optional roles
                        if tr1<0 or tr1>rolCostBd[role]:
                            tr1=rolCostBd[role]
                            j=role # role of min cost
                if  tr1>0:
                    assert j>=0
                    nbCompr-=1
                    if bdCost>0:
                        bdCost += tr1
                    else:
                        bdCost = tr1
                    rolCostBd[j]=-1

        if nbCompr>0 and tcost<0 :
            return -1 # not enough of bad data and impossible to compromise manadatory roles  
        if tcost<0 :
            if bdCost<0:
                return activityCost
            return activityCost + bdCost
        if bdCost>=0:
            if tcost<bdCost:
                return activityCost+tcost           
            return activityCost+bdCost
        return activityCost+tcost 


 
    def costCodeInjection(self,role, targetState: Location) ->int:
        if targetState==Location.MALW:
            if self.node.roles[role].mCodeInjectCost is None: 
                return -1
            else:
                return self.node.roles[role].mCodeInjectCost 
        if targetState==Location.BADD:
            if self.node.roles[role].bCodeInjectCost is None: 
                return -1
            else:
                return self.node.roles[role].bCodeInjectCost 
           
        if targetState==Location.NOAV:
            if self.node.roles[role].nCodeInjectCost is None: 
                return -1
            else:
                return self.node.roles[role].nCodeInjectCost 
        return -1
          
    def MinCostMalware(self,targetState:Location) -> int :
        cost:int=-1
        if self.node.nbInputs is None : 
            return -1
        if self.node.nbInputs <=0 :
            return -1  
        for i in range(self.node.nbInputs):
            sourceNodeIndex:int=self.node.inputs[i].sourceNodeIndex 
            if self.isOpenL[i]() and (self.currentLoc[sourceNodeIndex]==Location.MALW or (self.currentLoc[sourceNodeIndex]==Location.BADD and self.node.inputs[i].position=="peer") ):
                role:int= self.node.inputs[i].roleIndex 
                tcost:int=self.ProtProtectCost(i,role,sourceNodeIndex,self.node.inputs[i].position) 
                if tcost>=0:
                    injCost:int=self.costCodeInjection(role,targetState)
                    if injCost>=0:
                        tcost+=injCost
                        if cost<0 or cost>tcost:
                            cost=tcost 
        return cost



    def f2Mguard(self) -> int :
            return self.MinCostMalware(Location.MALW)
    def f2Bguard(self) -> int :
        if self.node.nodeType=="kernel":
            return -1
        ib:int=self.minBadDataCost()
        im:int=self.MinCostMalware(Location.BADD)
        if ib<0 or (im>=0 and im<ib):
            return im
        return ib
    
    def f2Nguard(self) -> int :
            minNonDisp:int=self.minNonDispCost()
            minCostMal=self.MinCostMalware(Location.NOAV)
            if minNonDisp<0 or minCostMal<minNonDisp:
                return minCostMal
            return minNonDisp

    def locSecrGaurd(self) -> int :
        nodeIndex:int=self.nodeIndex
        if self.model.nbSecrets is None or self.node.secrTheftCost is None:
            return -1
        assert self.model.nbSecrets >=0 
        for i in range(self.model.nbSecrets): 
                if self.model.nodes[nodeIndex].secrStore[i] and not self.currentSecr[i]: 
                    return self.node.secrTheftCost
        return -1


    def remSecrGaurd(self) -> int :
        nodeIndex:int=self.nodeIndex
        if self.model.nbSecrets is None or self.node.nbInputs is None :
            return -1
        assert self.model.nbSecrets >=0 and self.node.nbInputs >=0
        toSteal:bool=False
        for i in range(self.model.nbSecrets): 
            if self.model.nodes[nodeIndex].secrStore[i] and not self.currentSecr[i]: 
                toSteal=True
        if not toSteal:
            return -1
        cost:int=-1
        for i in range(self.node.nbInputs):
            sourceNodeIndex:int=self.node.inputs[i].sourceNodeIndex 
            if self.isOpenL[i]() and  self.currentLoc[self.node.inputs[i].sourceNodeIndex]==Location.MALW: 
                role:int= self.node.inputs[i].roleIndex 
                tcost:int=self.ProtProtectCost(i,role,sourceNodeIndex,self.node.inputs[i].position) 
                if tcost>=0 and self.node.roles[role].remoteSecrTheftCost is not None: 
                    assert self.node.roles[role].remoteSecrTheftCost >=0  # type: ignore
                    tcost+=self.node.roles[role].remoteSecrTheftCost  # type: ignore
                    if cost<0 or cost>tcost:
                        cost=tcost 
        return cost


    def f2MfallBackGuard(self) -> int :
        costByPass:Optional[int]=None
        costByPass=self.node.monBypassCost.toM 
        if costByPass is None:
            return -1
        assert costByPass>=0   
        cost:int = self.MinCostMalware(Location.MALW)
        if cost > 0 :
            return cost+costByPass
        else:
            return -1
        
    def f2BfallBackGuard(self) -> int :
        if self.node.nodeType=="kernel":
            return -1        
        costByPass:Optional[int]=self.node.monBypassCost.toB 
        if costByPass is None:
            return -1
        assert costByPass>=0   
        ib:int=self.minBadDataCost()
        im:int=self.MinCostMalware(Location.BADD)
        if ib<0 or (im>=0 and im<ib):
            if im<0:
                return -1
            return im + costByPass
        return ib+costByPass


    def f2NfallBackGuard(self) -> int :
        costByPass:Optional[int]=self.node.monBypassCost.toN 
        if costByPass is None:
            return -1
        assert costByPass>=0
        minNonDisp:int = self.minNonDispCost()  
        costMal:int = self.MinCostMalware(Location.NOAV)
        if costMal<0 or (minNonDisp>=0 and minNonDisp<costMal):
            if minNonDisp <0:
                return -1
            return minNonDisp+costByPass
        return costMal+costByPass

    def __init__(
        self,
        modelEnv: Model,
        nodeIndex: int,
        currentLoc: List[Location],
        currentSecr: List[bool],
        nodeIndexByName: dict[str,int],
        secrIndexByname: dict[str,int],
        fallbackActions: List[Actions],
        transIndex:int
    ):
        Template.__init__(self, modelEnv, nodeIndex, currentLoc, currentSecr,nodeIndexByName, secrIndexByname,fallbackActions,transIndex)

        if self.node.nbInputs is None:
            return
        if self.node.nbInputs == 0:
            return
        assert self.node.nbInputs > 0 
        # self.automaton:dict[Location,List[Transition]]={}
        # 
        #  Creation of the automaton according to the model!!!!
        
        # Defintion of transitions for all Loactions the model uses 
        #
        #  
        #  for Location.FUNC


        # ALL LOCATIONS HAVE TO BE FULL FULFILLED  to keep the compatibility with KERAS and q-learning !!!!!

        # transIndex:int index within the entire system transitions
        
        trasL:List[Transition]=[] 
           #  for transition to Location.MALW
        actions=Actions()
        actions.transitions.append(Trans(nodeIndex,Location.MALW))
        trasL.append(Transition("F2M",self.f2Mguard,actions,transIndex))
        transIndex+=1
            #  for transition to Location.BADD
        actions=Actions()
        actions.transitions.append(Trans(nodeIndex,Location.BADD))
        trasL.append(Transition("F2B",self.f2Bguard,actions,transIndex))
        transIndex+=1
             #  for transition to Location.NOAV
        actions=Actions()
        actions.transitions.append(Trans(nodeIndex,Location.NOAV))
        trasL.append(Transition("F2N",self.f2Nguard,actions,transIndex))
        transIndex+=1
            #  for transitions avec fallbacks
        if self.fallbackActions is not None:
            if self.toMfallbackActInd is not None:
                trasL.append(Transition("FallF2M",self.f2MfallBackGuard,self.fallbackActions[self.toMfallbackActInd],transIndex))
                transIndex+=1 
            if self.toBfallbackActInd is not None:
                trasL.append(Transition("FallF2B",self.f2BfallBackGuard,self.fallbackActions[self.toBfallbackActInd],transIndex))
                transIndex+=1
            if self.toNfallbackActInd is not None:
                trasL.append(Transition("FallF2N",self.f2NfallBackGuard,self.fallbackActions[self.toNfallbackActInd],transIndex))
                transIndex+=1    
            #  for remote secr theft !!!! ajouter la prise en compte du kernel !!!!!
        actions=Actions()
        if self.model.nodes[nodeIndex].secrStore is not None: 
            l1:bool=False
            for i in range(len(self.model.nodes[nodeIndex].secrStore)): 
                if self.model.nodes[nodeIndex].secrStore[i] : 
                    l1=True
                    actions.secretChange.append(SetSecr(i,True))
            if l1:
                trasL.append(Transition("RemTheft",self.remSecrGaurd,actions,transIndex))
                transIndex+=1
        
        self.automaton[Location.FUNC]=trasL

        #  for Location.MALW
        # 
        trasL:List[Transition]=[] 

            #  for loc secr theft !!!! ajouter la prise en compte du kernel !!!!!
        actions=Actions()
        if self.model.nodes[nodeIndex].secrStore is not None: 
            l1:bool=False
            for i in range(len(self.model.nodes[nodeIndex].secrStore)): 
                if self.model.nodes[nodeIndex].secrStore[i] : 
                    l1=True
                    actions.secretChange.append(SetSecr(i,True))
            if l1:
                trasL.append(Transition("LocTheft",self.remSecrGaurd,actions,transIndex))
                transIndex+=1
        
        self.automaton[Location.MALW]=trasL

        #  for Location.BADD
        # 
        trasL:List[Transition]=[] 
           #  for transition to Location.MALW
        actions=Actions()
        actions.transitions.append(Trans(nodeIndex,Location.MALW))
        trasL.append(Transition("B2M",self.f2Mguard,actions,transIndex))
        transIndex+=1
             #  for transition to Location.NOAV
        actions=Actions()
        actions.transitions.append(Trans(nodeIndex,Location.NOAV))
        trasL.append(Transition("B2N",self.f2Nguard,actions,transIndex))
        transIndex+=1
            #  for transitions avec fallbacks
        if self.fallbackActions is not None:
            if self.toMfallbackActInd is not None :
                trasL.append(Transition("FallB2M",self.f2MfallBackGuard,self.fallbackActions[self.toMfallbackActInd],transIndex)) 
                transIndex+=1
            if self.toNfallbackActInd is not None:
                trasL.append(Transition("FallB2N",self.f2NfallBackGuard,self.fallbackActions[self.toNfallbackActInd],transIndex)) 
                transIndex+=1
        
        actions=Actions()
        if self.model.nodes[nodeIndex].secrStore is not None: 
            l1:bool=False
            for i in range(len(self.model.nodes[nodeIndex].secrStore)): 
                if self.model.nodes[nodeIndex].secrStore[i] :
                    l1=True
                    actions.secretChange.append(SetSecr(i,True))
            if l1:
                trasL.append(Transition("Remote Theft",self.remSecrGaurd,actions,transIndex))
                transIndex+=1
        
        self.automaton[Location.BADD]=trasL




