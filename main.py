
# 原材料物控分析系统 V1.0

material = "电解液"
demand = 500
stock = 200
incoming = 100

shortage = max(0, demand - stock - incoming)

print("原材料物控分析系统")
print("物料名称：", material)
print("需求数量：", demand, "kg")
print("合格库存：", stock, "kg")
print("预计到货：", incoming, "kg")
print("预计缺口：", shortage, "kg")
