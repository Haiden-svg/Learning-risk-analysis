const int NU = -1;
const int pF = 0;
const int pP = 1;
const int pA = 2;
// FIXME: define cK, cU, sF, sB, sM, sN, rS, rA (others?)
// TODO: shall we use only values <0 for constants?
//       At least ensure that const names are always used

// input description, for each interaction
typedef struct {
  // input node id
  int[NU, SYSTEM.nbNodes-1] node_id;
  // - pF 0 == Functional
  // - pP 1 == Path
  // - pA 2 == Access
  int[NU, 2] attack_position;
  // role id of attacked component, local id
  int [0, NAMEDNODE.diMr] roleId;
  // attack on protocols:
  // [0] session entrance cost (0 for pF)
  // [1] deny of service (both already adapted to the attacker position)
  int protCost[2];
} input_t;

// node description, for topology
typedef struct {
  // numeric id of the node
  int[0, SYSTEM.nbNodes-1] node_id;
  // type for the node:
  // - 0 == user space component
  // - 1 == root space component
  // - 2 == kernel
  int[0, 2] node_type; 
  // min of Bd roles to be bad data
  int minInputBd;
  // min of active rA roles != 'mandatory' to be sF or sB,
  // mandatory roles no included
  int minInput;
  // steal all the secrets stored locally, by already installed local malware
  // FIXME: define MaxUnitCost
  int[NU, MaxUnitCost] costVarGet;
  // if true, secret to be retrieved here
  bool locSecretVar[SYSTEM.nbVar];
  // 3 costs for bypassing anomaly detection, if <0, monitoring disabled:
  // [0] m
  // [1] b
  // [2] n 
  int AnomDetParam[3];
  // role params:
  // [0] role type: rA==app rS==system
  // [1] importance (!= NU only for rA)
  //     - Nu=='do not consider'
  //     - 0=='no mandatory'
  //     - 1=='must be active'
  // [2] bad data acceptability cost
  // [3-5] 3 malware install costs: m, b, n
  // [6] cost of theft of locally stored secrets by remote malware
  // |7] key number protecting the role (i.e. if the attacker already
  //     has the key, attacking the session will cost zero) we consider that
  //     producing non acceptable bad data costs nothing!!!
  int RoleParams[NAMEDNODE.diMr][8];
  input_t in[NAMEDNODE.diM];
} node_t;

typedef struct {
  char* node_name;
  int diMr;
  int diM;
  node_t node;
  // TODO: check if size is really .diM
  char* is_open[NAMEDNODE.diM];
} namedNode_t;

typedef struct {
  int nbNodes;
  int nbVar;
  int fallBackMode[SYSTEM.nbNodes][3];
  namedNode_t nodes[SYSTEM.nbNodes];
} system_t;

{	// system_t
	14, // .nbNodes
  5,	// .nbVar
	{ // .fallBackMode
    // fallback number for sM, sB or sN locations
    {NU, NU, NU}, // node: 0:  ExtBrowser
    {NU, NU, NU}, // node: 1:  KCustExt
    {NU, NU, NU}, // node: 2:  KextHack
    {1,  1,  NU}, // node: 3:  FfM
    {NU, NU, NU}, // node: 4:  App
    {NU, NU, NU}, // node: 5:  IntraBrowser
    {NU, NU, NU}, // node: 6:  KCustIn
    {NU, NU, NU}, // node: 7:  KIntHack
    {NU, NU, NU}, // node: 8:  Internet
    {NU, NU, NU}, // node: 9:  KfM
    {NU, NU, NU}, // node: 10: KServ1
    {NU, NU, NU}, // node: 11: ServHttp1
    {NU, NU, NU}, // node: 12: KServ2
    {NU, NU, NU}, // node: 13: ServHttp2
	}, // FIXME: ',' was missing
	{ // namedNode_t
		"KextHack", // .name
    1,          // .diMr
    10,	        // .diM
    { // node_t
      2,  // .node_id
      cK, // .node_type
      1,  // .minInputBd
      0,  // .minInput
      -1, // .costVarGet, TODO: -1/NU
      {   // .locSecretVar
        false, false, false, false, false
      },
      { // .AnomDetParam, TODO: -1/NU
        -1, -1, -1
      },
		{ // .RoleParams, TODO: -1/NU?
			{ rS, -1, -1, 25, -1, 18, -1, -1}
		},
		{ // .in
			{ // input_t
        0,        // .node_id
        pF,       // .attack_position
        0,        // .roleId
        { -1, -1} // .protCost, TODO: -1/NU
      },
			{3,  pF, 0, {-1, -1}}, // TODO: -1/NU
			{8,  pF, 0, {-1, -1}},
			{1,  pF, 0, {-1, -1}},
			{6,  pF, 0, {-1, -1}},
			{7,  pF, 0, {-1, -1}},
			{10, pF, 0, {-1, -1}},
			{12, pF, 0, {-1, -1}},
			{9,  pF, 0, {-1, -1}},
			{13, pF, 0, {-1, -1}}
		}
	},
  { // .is_open, TODO: int state[SYSTEM.nbNodes] => contains constants s* 
    "( state[8] != sN and  state[1] != sN and  state[2] != sN)",
    "( state[8] != sN and  state[3] != sN and  state[2] != sN)",
    "( state[8] != sN and  state[2] != sN)",
    "( state[8] != sN and  state[1] != sN and  state[2] != sN)",
    "( state[8] != sN and  state[3] != sN and  state[9] != sN and  state[6] != sN and  state[2] != sN)",
    "( state[8] != sN and  state[3] != sN and  state[9] != sN and  state[7] != sN and  state[2] != sN)",
    "( state[8] != sN and  state[3] != sN and  state[9] != sN and  state[10] != sN and  state[2] != sN)",
    "( state[8] != sN and  state[3] != sN and  state[9] != sN and  state[12] != sN and  state[2] != sN)",
    "( state[8] != sN and  state[3] != sN and  state[9] != sN and  state[2] != sN)",
    "( state[8] != sN and  state[3] != sN and  state[9] != sN and  state[12] != sN and  state[2] != sN)"
		}
	},
  // ... other nodes
}
