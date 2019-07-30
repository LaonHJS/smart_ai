from collections import defaultdict
from problemIO.product import *
from problemIO.lot import *
from problemIO.resource import *
from copy import deepcopy as cp
from simulator.simRecord import *
from simulator.gen_data import *
from mysql.connector import errorcode

class ProductionInfo(object):
    def __init__(self):
        self.DBTableName = "big_youth"
        self.config = 0

        self.productionRequirement = defaultdict(dict)
        self.intarget = defaultdict(dict)
        self.intarget_total = defaultdict(dict)
        # self.WIP = {}
        self.constraints = {}
        self.options = {}

        self.productMap = {}
        self.operationTypeMap = {}
        #  Key들은 모두 String
        self.operationMap = {}
        self.resourceModelMap = {}
        self.resourceMap = {}
        self.lotMap = {}
        self.flowMap = {}
        self.eventList = []

        # DB에서 읽어와서 여기에 할당해 주어야 함
        self.moveTime = 0
        self.DASTRatio = 0.0
        self.WBSTRatio = 0.0
        self.simulDay = 0
        # Index Dictionary
        # self.resourceIndexMap = {}
        # self.resourceIDMap = {}

        # for normalization of state and score
        self.needStateNormalization = False
        self.needScoreNormalization = False
        self.needDAWaitingNormalization = False
        self.normalizationMap = {}
        self.scoreCriteriaMap = defaultdict(dict)
        self.state_nor = None
        self.score_nor = None
        self.DA_score_nor = None

    def getInfor(self):
        for flowID in self.flowMap.keys():
            print(flowID + "\t")
            print(*self.flowMap[flowID].operationSequence, sep = '\t')
        for productID in self.productMap.keys():
            product = self.productMap[productID]
            print(product.getInfor())
        for modelID in self.resourceModelMap.keys():
            model = self.resourceModelMap[modelID]
            print(model.getInfor())


class ProblemReaderDB():

    flowTable = "FlowTypes"
    productTable = "ProductTypes"
    operationTable = "ex_OperationTypes"
    resourceModelTable = "ResourceModels"
    arrangementTable = "ResourceArrangementTypes"
    denominator = "\r\n"

    def callDB(self, address, id, pw, DBname):
        try:
            return mysql.connect(host=address, user=id, password=pw, database=DBname)
        except mysql.Error as err:
            if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
                print("Something is wrong with your user name or password")
            elif err.errno == errorcode.ER_BAD_DB_ERROR:
                print("Database does not exist")
            else:
                print(err)

    def __init__(self, tableName, address='121.165.19.66', id='student', pw='big1234', DBname='big_youth'):
        con = self.callDB(address, id, pw, DBname)
        cur = con.cursor()

        self.pi = ProductionInfo()

        sql = "select flowID, operationSequence from " + ProblemReaderDB.flowTable
        cur.execute(sql)
        for (flowID, operationSequence) in cur:
            flow = Flow(flowID, operationSequence)
            self.pi.flowMap[flowID] = flow

        sql = "select * from " + ProblemReaderDB.productTable
        cur.execute(sql)
        # use fetchone()
        row = cur.fetchone()
        while row is not None:
            productID = row[1]
            flowID = row[4]
            product = Product(productID, row[2], row[3], flowID, row[5], row[6], row[7], row[8], self.pi.flowMap[flowID])
            self.pi.productMap[row[1]] = product
            row = cur.fetchone()

        sql = "select operationID, operationName, operationBufferTime from " + ProblemReaderDB.operationTable
        cur.execute(sql)
        for (operationID, operationName, operationBufferTime) in cur:
            operation = Operation(operationID, operationName, operationBufferTime)
            self.pi.operationTypeMap[operationID] = operation

        sql = "select * from " + ProblemReaderDB.arrangementTable
        cur.execute(sql)
        resource_arrangement_map = {}

        row = cur.fetchone()
        while row is not None:
            index = row[0]
            ra = ResourceArrangement(index, row[1], row[2], row[3], row[4], row[5], row[6], row[7])
            resource_arrangement_map[index] = ra
            row = cur.fetchone()

        sql = "select * from " + ProblemReaderDB.resourceModelTable
        cur.execute(sql)

        row = cur.fetchone()
        while row is not None:
            modelId = row[1]
            rm = ResourceModel(modelId, row[6], resource_arrangement_map)
            rm.setSetupTime(row[2], row[3], row[4])
            self.pi.resourceModelMap[modelId] = rm
            row = cur.fetchone()

        for index in resource_arrangement_map.keys():
            ra = resource_arrangement_map[index]
            assert isinstance(ra, ResourceArrangement)
            temp_product = self.pi.productMap[ra.productId]
            assert isinstance(temp_product, Product)
            temp_product.addArrangement(ra.operationId, self.pi.resourceModelMap[ra.resourceModelId])

        self.problemSetMap = {}
        if tableName != '':
            sql = "select * from " + tableName
            cur.execute(sql)
            # use fetchall()
            rows = cur.fetchall()
            denominator = self.denominator

            # column단위로 자르는 부분, np로 대체 가능?
            idx = [row[0] for row in rows]
            layoutType = [row[1] for row in rows]
            moveTime = [row[2] for row in rows]
            timeHorizon = [row[3] for row in rows]
            simulDay = [row[4] for row in rows]
            DASTRatio = [row[5] for row in rows]
            WBSTRatio = [row[6] for row in rows]
            target = [row[7] for row in rows]
            resourceStatus = [row[8] for row in rows]
            lotStatus = [row[9] for row in rows]
            wip = [row[10] for row in rows]
            setupSchedule = [row[11] for row in rows]
            forNormalization = [row[12] for row in rows]
            rewardCriteria = [row[13] for row in rows]
            DA_waiting = [row[14] for row in rows]
            for i in range(len(idx)):
                problemInstance = ProblemSet(idx[i],layoutType[i],moveTime[i],timeHorizon[i],simulDay[i],DASTRatio[i],WBSTRatio[i],
                                             None if wip[i]==None else wip[i].rstrip(denominator).split(denominator),
                                             target[i].rstrip(denominator).split(denominator),
                                             resourceStatus[i].rstrip(denominator).split(denominator),
                                             lotStatus[i].rstrip(denominator).split(denominator),
                                             None if setupSchedule[i] == None else setupSchedule[i].rstrip(denominator).split(denominator),
                                             None if forNormalization[i] == None else forNormalization[i].rstrip('\n').split('\n'),
                                             None if rewardCriteria[i] == None else rewardCriteria[i].rstrip('\n').split('\n'),
                                             None if DA_waiting[i] == None else DA_waiting[i].rstrip('\n').split('\n'))

                self.problemSetMap[idx[i]] = problemInstance
        cur.close()
        con.close()

    def generateProblem(self, idx, presolving):
        #first set problem-independent production info
        result = cp(self.pi)
        result.config = idx
        problemInstance = self.problemSetMap[idx]
        assert isinstance(problemInstance, ProblemSet)

        # Set problem-dependent production info from problemInstance
        result.moveTime = problemInstance.moveTime
        result.DASTRatio = problemInstance.DASTRatio
        result.WBSTRatio = problemInstance.WBSTRatio
        result.simulDay = problemInstance.simulDay
        result.productionRequirement, result.intarget = self.setTarget(problemInstance.target, problemInstance.simulDay)
        result.lotMap = self.setLot(problemInstance.lotStatus, problemInstance.wip, problemInstance.simulDay, result.productionRequirement)
        result.resourceMap = self.setResource(problemInstance.resourceStatus, result.lotMap)
        result.eventList = self.setEvent(result, problemInstance.resourceStatus, problemInstance.setupSchedule)

        if problemInstance.forStateNormalization is None:
            result.needStateNormalization = True
            result.state_nor = NormalForState(idx, 'DA')
        else:
            temp_list = problemInstance.forStateNormalization
            mean = [float(x) for x in temp_list[0].rstrip('\t').split('\t')]
            std = [float(x) for x in temp_list[1].rstrip('\t').split('\t')]
            max_vector = [float(x) for x in temp_list[2].rstrip('\t').split('\t')]
            min_vector = [float(x) for x in temp_list[3].rstrip('\t').split('\t')]
            result.state_nor = NormalForState(idx, 'DA', mean, std, max_vector, min_vector)

        if problemInstance.forScoreNormalization is None:
            result.needScoreNormalization = True
            result.score_nor = NormalForScore(idx, 'DA_score')
        else:
            temp_list = problemInstance.forScoreNormalization
            median = [float(x) for x in temp_list[0].rstrip('\t').split('\t')]
            mean = [float(x) for x in temp_list[1].rstrip('\t').split('\t')]
            std = [float(x) for x in temp_list[2].rstrip('\t').split('\t')]
            max_vector = [float(x) for x in temp_list[3].rstrip('\t').split('\t')]
            min_vector = [float(x) for x in temp_list[4].rstrip('\t').split('\t')]
            result.score_nor = NormalForScore(idx, median, mean, std, max_vector, min_vector)

        if problemInstance.forDAWaiting is None:
            result.needDAWaitingNormalization = True
            result.DA_score_nor = NormalDAWaitingScore(idx)
        else:
            temp_list = problemInstance.forDAWaiting
            median = [float(x) for x in temp_list[0].rstrip('\t').split('\t')]
            mean = [float(x) for x in temp_list[1].rstrip('\t').split('\t')]
            std = [float(x) for x in temp_list[2].rstrip('\t').split('\t')]
            max_vector = [float(x) for x in temp_list[3].rstrip('\t').split('\t')]
            min_vector = [float(x) for x in temp_list[4].rstrip('\t').split('\t')]
            result.DA_score_nor = NormalDAWaitingScore(idx, median, mean, std, max_vector, min_vector)

        return result

    def setLot(self, lotStatus, wip, simulDay, productionRequirement):
        lotMap = {}
        # for d in range(simulDay):
        for d in range(1):
            for alotStatus in lotStatus:
                lotInfo = alotStatus.split("\t")
                lotId = lotInfo[0]+'D'+str(d+1)
                productId = lotInfo[1]
                lotQ = int(lotInfo[2])
                lotPriority = int(lotInfo[3])
                dueDate = int(lotInfo[4])+d*86400
                inTime = int(lotInfo[5])+d*86400
                loc = lotInfo[6]
                if loc == 'DA_STOCK':
                    loc = 'CST_STOCK'
                flowId = self.pi.productMap[productId].flowId
                flowNum = 0  # WIP이 아닌 투입계획 Lot들이므로
                newLot = Lot(lotId, productId, flowId, flowNum, lotQ, lotPriority, dueDate, inTime, loc)
                lotMap[lotId] = newLot
        if wip is None: return lotMap
        for awip in wip:
            wipInfo = awip.split("\t")
            wipId = wipInfo[0]
            productId = wipInfo[1]
            lotQ = int(wipInfo[2])
            lotPriority = 1
            flowNum = int(wipInfo[3])
            dueDate = int(wipInfo[4])
            inTime = int(wipInfo[5])
            loc = wipInfo[6]
            flowId = self.pi.productMap[productId].flowId
            newWipLot = Lot(wipId,productId,flowId,flowNum,lotQ,lotPriority,dueDate,inTime,loc)
            lotMap[wipId] = newWipLot
            if '_' not in wipId:
                productionRequirement[productId] = productionRequirement[productId]+lotQ

        return lotMap

    def setTarget(self, target, simulDay):
        productionRequirement = {}
        for i in range(len(target)):
            productTarget = target[i].split("\t")
            productId = productTarget[0]
            requirement = int(productTarget[1]) * simulDay
            if requirement > 0:
                productionRequirement[productId] = requirement
                for day in range(simulDay):
                    self.pi.intarget[productId][day] = int(productTarget[1])
        return productionRequirement, self.pi.intarget

    def setResource(self, resourceStatus, lotMap):
        resourceMap = {}
        for i in range(len(resourceStatus)):
            resourceInfo = resourceStatus[i].split("\t")
            resId = resourceInfo[0]
            resOperationId = resId.split("_")[0]
            resModelId = resourceInfo[1]
            resStatus = resourceInfo[2]
            lotIdProcess = resourceInfo[3]
            setuped_operation = resourceInfo[4]
            # timestamp = int(resourceInfo[5])
            if resStatus=='RUN':
                nowLot = lotMap[lotIdProcess]
                assert isinstance(nowLot, Lot)
                productIdProcess = nowLot.productId
                nowLot.changeLotStatus('PROCESS', nowLot.lotLocation, resOperationId, resId)
            else:
                productIdProcess = lotIdProcess
                lotIdProcess = ''

            resourceMap[resId] = Resource(resId, resModelId, resOperationId, resStatus, productIdProcess, lotIdProcess,
                                          productIdProcess, setuped_operation) #우선 setupStatus에 productId를 넣고, initialize에서 일괄처리
        return resourceMap

    def setEvent(self, productionInfo, resourceStatus, setupSchedule):
        eventlist = []
        idx = 0

        # initial events in resource
        # See JSim.initialize() for initial events in lot

        for i in range(len(resourceStatus)):
            resourceInfo = resourceStatus[i].split("\t")
            resId = resourceInfo[0]
            lotId = resourceInfo[3]
            resStatus = resourceInfo[2]
            # timestamp = int(resourceInfo[5])
            timestamp = 0
            if resStatus == 'RUN':
                operationId = productionInfo.lotMap[lotId].currentOperationId
                event = Event(idx, operationId, lotId, resId, "TrackInFinish", 0, timestamp)
                idx += 1
                eventlist.append(event)
            else:
                if resStatus == 'SETUP':
                    event = Event(idx, '', lotId, resId, "SetupChangeFinish", 0, timestamp)
                    idx += 1
                    eventlist.append(event)

        # Scheduled events in resource (Setup)
        # Setup을 PG수준에서 given으로 만드는 경우에 필요

        return eventlist


class ProblemSet:
    def __init__(self, id, layoutType, moveTime, horizon, simulDay, DASTRatio, WBSTRatio, wip, target, resourceStatus,
                 lotStatus, setupSchedule, forNormalization, rewardCriteria, DA_waiting=None):
        self.idx = id
        self.layoutType = layoutType
        self.moveTime = moveTime
        self.horizon = horizon
        self.simulDay = simulDay
        self.DASTRatio = DASTRatio
        self.WBSTRatio = WBSTRatio
        self.wip = wip
        self.target = target
        self.resourceStatus = resourceStatus
        self.lotStatus = lotStatus
        self.setupSchedule = setupSchedule
        self.forStateNormalization = forNormalization
        self.forScoreNormalization = rewardCriteria
        self.forDAWaiting = DA_waiting


