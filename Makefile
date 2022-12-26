TARGET_DIR=/Volumes/CIRCUITPY
LIB_DIR=$(TARGET_DIR)/lib

LIBS=$(addprefix $(LIB_DIR)/, neopixel.mpy)

install: statemachines
	rsync -a $< $(LIB_DIR)

clean:
	rm -f $(TARGET_DIR)/code.py
	rm -rf $(LIB_DIR)

$(TARGET_DIR)/lib/%: lib/%
	rsync -a $< $(TARGET_DIR)/lib

$(LIB_DIR): 
	mkdir $@

$(LIBS): | $(LIB_DIR)

traffic: $(LIBS) install tests/traffic.py
	cp tests/traffic.py $(TARGET_DIR)/code.py

flicker: $(LIBS) install tests/flicker_test.py install
	cp tests/flicker_test.py $(TARGET_DIR)/code.py

