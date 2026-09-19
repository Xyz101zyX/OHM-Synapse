import ohm_synapse
print("OK - ohm_synapse imported")
print("version:", ohm_synapse.OHM_VERSION)
brain = ohm_synapse.OHMSynapse()
r = brain.think("/help")
print("status:", r.status)
print("confidence:", r.confidence)
brain.shutdown()
print("OK - pipeline works")