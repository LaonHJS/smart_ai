from collections import defaultdict


class Product(object):
    def __init__(self, productId, productName, productGroup, flowId, minCSTLotSize, maxCSTLotSize,
                 minMGZLotSize, maxMGZLotSize, operationSequence):
        self.productId = productId
        self.productName = productName
        self.productGroup = productGroup
        self.flowId = flowId
        self.minCSTLotSize = minCSTLotSize
        self.maxCSTLotSize = maxCSTLotSize
        self.minMGZLotSize = minMGZLotSize
        self.maxMGZLotSize = maxMGZLotSize
        self.operationSequence = operationSequence
        self.feasibleResourceModelMap = defaultdict(list)

    def addArrangement(self, operation, resourceModel):
        self.feasibleResourceModelMap[operation].append(resourceModel)

    def getInfor(self):
        return "productTypeId\t" + self.productId + "\n" + "productTypeName\t" + self.productName + "\n" + \
               "productGroup\t" + self.productGroup + "\n" + "productGroupName\t" + self.productGroup + "\n" + \
               "flowId\t" + self.flowId


""" ------------------------ Flow (보형이에게 질문 할 게 있음) ------------------------ """


class Flow(object):
    def __init__(self, flowId, sequences):
        self.flowId = flowId
        self.operationSequence = sequences.split(",")

    def getNextOperationForState(self, flowNumber):
        if flowNumber == len(self.operationSequence) - 1:
            return ""
        now = self.operationSequence[flowNumber]
        next_ = self.operationSequence[flowNumber + 1]
        # 이 if 문은 어떤걸 의도한 건지??? -> DDW 때문에 처리한 것
        if "DA" in now and "DA" in next_:
            return self.operationSequence[flowNumber + 2]
        else:
            return next_

    def getNowOperation(self, flowNumber):
        if flowNumber >= len(self.operationSequence):
            return "SHIP"
        elif flowNumber < 0:
            return ""
        return self.operationSequence[flowNumber]

    def getLotFlowName(self, flowNumber, productType):
        return productType + str(flowNumber)

    def getLotFlowDegree(self, flowNumber):
        degree = 1
        for i in range(0, flowNumber):
            if "WB" in self.operationSequence[i]:
                degree = degree + 1
        return degree

    def getCompletedFlowNum(self, flowNumber, operationType):
        degree = 0
        for i in range(0, flowNumber):
            if operationType in self.operationSequence[i]:
                degree = degree + 1
        return degree

    def getMaxFlowDegree(self, operationType):
        degree = 0
        for i in range(len(self.operationSequence)):
            if operationType in self.operationSequence[i]:
                degree = degree + 1
        return degree

    def getTotalFlowDegree(self):
        return len(self.operationSequence)

    # 현재 flowNumber도 아직 하지 않은 operation으로 취급
    def getRemainingOperations(self, flowNumber):
        remaining_DA_num = 0
        remaining_WB_num = 0
        for i in range(flowNumber, len(self.operationSequence)):
            now_operation = self.operationSequence[i]
            if 'DA' in now_operation:
                remaining_DA_num += 1
            elif 'WB' in now_operation:
                remaining_WB_num += 1

        return remaining_DA_num, remaining_WB_num

    # def getInfor(self):
    #     return "flowId\t"+self.flowId+"\n"+"operationSequence\t"+(operationSequence, sep = '\t')



""" ------------------------ Operation  ------------------------ """

class Operation(object):
    def __init__(self, operationId, operationName, operationBufferTime):
        self.operationId = operationId
        self.operationName = operationName
        self.operationBufferTime = operationBufferTime
        self.UOMOfTime = ''

