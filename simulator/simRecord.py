import sys
from collections import defaultdict
from problemIO.resource import *
from problemIO.lot import Lot
import sys, os
import errno


class Counter(object):
    def __init__(self):
        # Snap-shot counter 모든 key와 value가 Integer
        self.ShipCount = {}
        self.inTargetCount = {}

        # Product group 별 Intarget 진척률
        self.inTargetCompletion = defaultdict(lambda: defaultdict(int))
        self.cumulativeInTargetCompletion = defaultdict(int)
        self.inTargetCountByProduct = defaultdict(lambda: defaultdict(int))
        self.inTarget_decided = defaultdict(lambda: defaultdict(int))

        self.SplitCount = {}
        self.MergeCount = {}
        self.InputCount = {}
        self.previousWIPCount = -1
        self.WIPLevel = {}

        self.shipCounter = 0
        self.inTargetCounter = 0
        self.splitCounter = 0
        self.mergeCounter = 0
        self.inputCounter = 0
        self.workingDA = 0
        self.workingWB = 0
        self.mgzCount = 0
        self.mgzMoveCount = 0
        self.mgzDACount = 0
        self.daWIPLevel = {}
        self.wbWIPLevel = {}

        self.DAUtilizationPerTimestamp = {}
        self.WBUtilizationPerTimestamp = {}

        nested_dict = lambda: defaultdict(nested_dict)
        self.WIP_level_per_product = nested_dict()
        self.WIP_level_per_product_agg = nested_dict()
        self.WIP_level_per_operation = defaultdict(int)

        # For State Making
        self.total_lot_per_product = defaultdict(int)
        self.current_finished_lot_per_product = defaultdict(int)


class KPIs(object):
    def __init__(self):
        self.completedProductQuantity = defaultdict(int)
        self.Utilization = defaultdict(int)
        self.SetupRate = defaultdict(int)
        self.TATMap = defaultdict(int)
        self.waitingMap = defaultdict(int)


class GanttChart(object):
    def __init__(self):
        self.decisionList = []
        self.scheduleForResource = defaultdict(list)


class Gantt(object):
    def __init__(self, eventId, starting_time, ending_time, productId, lotId, quantity, degree, flow) :
        self.eventId = eventId
        self.starting_time = starting_time
        self.ending_time = ending_time
        self.productId = productId
        self.lotId = lotId
        self.quantity = quantity
        self.degree = degree
        self.flow = flow


class SolutionResult(object):
    def __init__(self):
        self.util = 0.0
        self.utilizationPerResource = defaultdict(float)
        self.utilizationPerOperation = defaultdict(float)
        self.utilizationPerModel = defaultdict(float)
        self.numberPerOperation = defaultdict(int)
        self.numberPerModel = defaultdict(int)
        self.idle_time_bottleneck = 0

        self.total_TAT = 0
        self.total_WaitingTime = 0
        self.avg_TAT = 0
        self.avg_WaitingTime = 0
        self.TATPerLot = defaultdict(int)
        self.avgTATPerProductId = defaultdict(int)
        self.maxTATPerProductId = defaultdict(int)
        self.minTATPerProductId = defaultdict(lambda: sys.maxsize)
        self.numberPerProduct = defaultdict(int)
        self.minLotIdPerProduct = {}
        self.maxLotIdPerProduct = {}
        self.intarget = defaultdict(lambda: defaultdict(int))
        self.inTargetCompletion = {}

    def setUtilRecord(self, currentResource, resUtil):
        assert isinstance(currentResource, Resource)
        resourceId = currentResource.resourceId
        self.utilizationPerResource[resourceId] = resUtil
        # Set per operation
        self.utilizationPerOperation[currentResource.operationId] += resUtil  # 잘 작동하면 냅두기
        self.numberPerOperation[currentResource.operationId] += 1
        # Set per Model
        self.utilizationPerModel[currentResource.resourceModelId] += resUtil
        self.numberPerModel[currentResource.resourceModelId] += 1

    def calUtilRecord(self):
        for modelId in self.utilizationPerModel.keys():
            self.utilizationPerModel[modelId] /= self.numberPerModel[modelId]
        for operationId in self.utilizationPerOperation.keys():
            self.utilizationPerOperation[operationId] /= self.numberPerOperation[operationId]

    def setTATRecord(self, currentLot, lotTAT):
        assert isinstance(currentLot, Lot)
        lotId = currentLot.lotId
        productId = currentLot.productId
        self.TATPerLot[lotId] = lotTAT
        self.numberPerProduct[productId] += 1
        self.avgTATPerProductId[productId] += lotTAT
        if self.minTATPerProductId[productId] > lotTAT:
            self.minTATPerProductId[productId] = lotTAT
            self.minLotIdPerProduct[productId] = lotId
        if self.maxTATPerProductId[productId] < lotTAT:
            self.maxTATPerProductId[productId] = lotTAT
            self.maxLotIdPerProduct[productId] = lotId

    def calTATRecord(self):
        for productId in self.avgTATPerProductId.keys():
            self.avgTATPerProductId[productId] /= self.numberPerProduct[productId]

    def store_inTarget(self, intarget, inTargetCompletion):
        for product_id, target_list in intarget.items():
            for index, target in enumerate(target_list):
                self.intarget[index][product_id] = target
        self.inTargetCompletion = inTargetCompletion

class Event(object):
    """
    FactoryInFinish = "FactoryInFinish"
    MoveFinish = "MoveFinish"
    TrackInFinish = "TrackInFinish"
    TrackOutFinish = "TrackOutFinish"
    TrackOutMoveFinish = "TrackOutMoveFinish"
    SplitFinish = "SplitFinish"
    MergeFinish = "MergeFinish"
    SetupChangeFinish = "SetupChangeFinish"

    Waiting = "Waiting"
    ReserveMoveWaiting = "ReserveMoveWaiting"       #기존 MoveWaiting에서 예약된 MoveWaiting을 따로 구분
    ReserveWaiting = "ReserveWaiting"
    SplitWaiting = "SplitWaiting"
    MoveWaiting = "MoveWaiting"
    MergeWaiting = "MergeWaiting"
    """

    def __init__(self, eventId, operationId, lotId, resourceId, type, start_time, period_time):
        self.eventId = eventId
        self.operationId = operationId
        self.lotId = lotId
        self.resourceId = resourceId
        self.type = type
        self.start_time = start_time
        self.period_time = period_time


class SetupRecord(object):
    def __init__(self, from_product, to_product, start_time):
        self.from_product = from_product
        self.to_product = to_product
        self.start_time = start_time


class decisionViewer(object):
    def __init__(self, decisionId, decisionTime, decisionType, lotId, lotStatus, decision,
                 operationId, productType, lotSize, wipLevel, dawipLevel,
                 wbwipLevel, workingDA, workingWB, inputCount, outputCount,
                 currentCSTQuantity, flowId, currentLocation, waiting, idle, d_waiting, loss):
        # Inherited Information
        self.decisionId = decisionId
        self.decisionTime = decisionTime
        self.decisionType = decisionType
        self.lotId = lotId
        self.lotStatus = lotStatus
        self.decision = decision
        self.operationId = operationId
        self.productType = productType
        self.lotSize = lotSize
        self.wipLevel = wipLevel
        self.dawipLevel = dawipLevel
        self.wbwipLevel = wbwipLevel
        self.workingDA = workingDA
        self.workingWB = workingWB
        self.inputCount = inputCount
        self.outputCount = outputCount
        self.currentCSTQuantity = currentCSTQuantity
        self.flowId = flowId
        self.currentLocation = currentLocation
        self.waiting = waiting
        self.idle = idle
        self.d_waiting = d_waiting
        self.loss = loss


class SSInstance(object):
    def __init__(self, state, lotId, resId, operationId, time, SVR=False):
        self.state = state
        self.lotId = lotId
        self.resId = resId
        self.operationId = operationId
        self.score = []
        self.time = time
        self.is_SVR = SVR

    def setReward(self, r):
        self.score = r


class DispatchingRecords(object):
    def __init__(self, filepath, denominator):
        self.Records = {}
        self.filepath = filepath
        self.denominator = denominator

    def addInstance(self, state, lotId, resId, operationId, time, SVR=False):
        self.Records[self.getKey(lotId, operationId)] = SSInstance(state, lotId, resId, operationId, time, SVR)

    def addReward(self, lotId, operationId, reward):
        instance = self.Records[self.getKey(lotId, operationId)]
        assert isinstance(instance, SSInstance)
        instance.setReward(reward)

    def getKey(self, lotId, operationId):
        return lotId + '_' + operationId

    def fileWrite(self, o='DA'):
        f = open(self.filepath+ '.csv', 'a')
        if 'check' in self.filepath and o == 'DA':
            att1 = range(14)
            att2 = ['loc1','loc2','loc3']
            msg = ''
            for key2 in att2:
                for key1 in att1:
                    msg += str(key1)+key2+','
            for i in range(8):
                msg += 'res'+str(i)+','
            for i in range(6):
                msg += 'act'+str(i)+','
            msg += '\n'
            f.write(msg)

        for key, instance in self.Records.items():
            if o not in key:
                continue
            if 'WIP' in key:
                continue
            assert isinstance(instance, SSInstance)
            info = []
            info.extend(instance.state)
            if instance.is_SVR:
                if instance.score < 1:
                    for i in range(len(info)):
                        if i < len(info) - 1:
                            f.write("%f," % info[i])
                        else:
                            f.write("%f\n" % info[i])
            else:
                info.extend(instance.score)
                for i in range(len(info)):
                    if info[i] > 100000000 :
                        info[i] = 0  # inf값이 들어가는 경우 예외처리 여기서 해줌
                    if i < len(info) - 1:
                        f.write("%f," % info[i])
                    else:
                        f.write("%f\n" % info[i])
        f.close()





