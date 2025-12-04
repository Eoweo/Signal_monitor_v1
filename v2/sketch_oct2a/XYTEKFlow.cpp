// Sky-Walkers 2021-2023
// Library for controlling XY-TEK flow sensor.

#include "Arduino.h"
#include "ModbusMaster2.h"  // MODBUS for Flow sensor
#include "XYTEKFlow.h"


XYTEKFlow::XYTEKFlow(HardwareSerial* serial_, uint8_t id_, void (*pre_transmission)(), void (*post_transmission)())
{
    serial = serial_;
    id = id_;

    serial->begin(115200);
    node.begin(id, *serial);  // communicate with Modbus slave ID over Serial port
                              // See how pointers work: https://stackoverflow.com/questions/4955198/what-does-dereferencing-a-pointer-mean/4955297

    node.preTransmission(pre_transmission);
    node.postTransmission(post_transmission);
}

// These functions must be defined in main program
//
// void flow_pre_transmission()
// {
// 	// Serial.println("PRE"); Serial.flush();
// 	digitalWrite(flow_re_neg_pin, 1);
// 	digitalWrite(flow_de_pin, 1);
// }
// void flow_post_transmission()
// {
// 	digitalWrite(flow_re_neg_pin, 0);
// 	digitalWrite(flow_de_pin, 0);
// 	// Serial.println("POST"); Serial.flush();
//
// 	/// PATCH for preceding zeros response
// 	long zero_patch_timeout_ms = 100;
// 	long zero_patch_t0 = millis();
// 	while (millis() - zero_patch_t0 < zero_patch_timeout_ms)
// 	{
// 		if (Serial2.available())
// 		{
// 			byte b = Serial2.peek();	// Keep byte in buffer
// 			if (b != 0)					// Valid byte
// 				break;					// Exit patch
// 			else
// 				Serial2.read();			// Flush byte and keep listening
// 		}
// 	}
// 	///
// }

bool XYTEKFlow::write_register(uint16_t data_address, uint16_t value)
{
    uint8_t result;
    result = node.writeSingleRegister(data_address, value);
    return result == node.ku8MBSuccess;
}


bool XYTEKFlow::write_registers(uint16_t data_address, uint16_t* data, uint16_t length)
{
    uint8_t result;
    for (uint8_t i = 0; i < length; i++)
        node.setTransmitBuffer(i, data[i]);
    result = node.writeMultipleRegisters(data_address, length);  // slave: write TX buffer to (2) 16-bit registers starting at register 0
    return result == node.ku8MBSuccess;
}


bool XYTEKFlow::read_registers(uint16_t data_address, uint16_t request_words)
{
    uint8_t result;
    result = node.readHoldingRegisters(data_address, request_words);  // slave: read (request_words) 16-bit registers starting at register (data_address) to RX buffer
    received_ok = result == node.ku8MBSuccess;
    if (received_ok)
    {
        for (uint8_t i = 0; i < request_words; i++)
            received_data[i] = node.getResponseBuffer(i);
        received_length = request_words;
    }
    return received_ok;
}

float XYTEKFlow::received_data_to_float(uint8_t offset)
{
    ftemp.u8[1] = highByte(received_data[0 + offset]);
    ftemp.u8[0] = lowByte(received_data[0 + offset]);
    ftemp.u8[3] = highByte(received_data[1 + offset]);
    ftemp.u8[2] = lowByte(received_data[1 + offset]);
    float float_var = ftemp.f;
    return float_var;
}


bool XYTEKFlow::search_device()
{
    // Should receive "XYKJ" = 0x4a4b5958
    read_registers(XYTEKFLOW_CMD_SEARCH_DEVICE[0], XYTEKFLOW_CMD_SEARCH_DEVICE[1]);
    if (received_ok)
        search_device_response = received_data[0] + received_data[1] << 16;
    return received_ok;
}

bool XYTEKFlow::read_status()
{
    read_registers(XYTEKFLOW_CMD_SYSTEM_STAT[0], XYTEKFLOW_CMD_SYSTEM_STAT[1]);
    if (received_ok)
        system_status = received_data[0];
    return received_ok;
}


bool XYTEKFlow::read_flowrate()
{
    //read_registers(XYTEKFLOW_CMD_USR_REQ_FLOW_RATE_REALTIME[0], XYTEKFLOW_CMD_USR_REQ_FLOW_RATE_REALTIME[1]);
    read_registers(XYTEKFLOW_CMD_USR_REQ_FLOW_RATE_AVG1S[0], XYTEKFLOW_CMD_USR_REQ_FLOW_RATE_AVG1S[1]);
    if (received_ok)
        flow_rate = received_data_to_float(0);
    return received_ok;
}
bool XYTEKFlow::read_volume_net()
{
    read_registers(XYTEKFLOW_CMD_USR_REQ_VOL[0], XYTEKFLOW_CMD_USR_REQ_VOL[1]);
    if (received_ok)
        flow_volume_net = received_data_to_float(0);
    return received_ok;
}
bool XYTEKFlow::read_volume_pos()
{
    read_registers(XYTEKFLOW_CMD_USR_REQ_POS_VOL[0], XYTEKFLOW_CMD_USR_REQ_POS_VOL[1]);
    if (received_ok)
        flow_volume_pos = received_data_to_float(0);
    return received_ok;
}
bool XYTEKFlow::read_volume_neg()
{
    read_registers(XYTEKFLOW_CMD_USR_REQ_NEG_VOL[0], XYTEKFLOW_CMD_USR_REQ_NEG_VOL[1]);
    if (received_ok)
        flow_volume_neg = received_data_to_float(0);
    return received_ok;
}


bool XYTEKFlow::reset_volume()
{
    return write_register(XYTEKFLOW_CMD_RESET_VOLUME[0], 1);
}

bool XYTEKFlow::zero_calibration()
{
    uint16_t u16_data[2];
    ftemp.f = 5.0f;  // Calibration time in seconds
    u16_data[0] = ftemp.u16[0];
    u16_data[1] = ftemp.u16[1];
    bool ok = write_registers(XYTEKFLOW_CMD_ZERO_CAL_TIME[0], u16_data, 2);
    if (ok)
    {
        delay(50);
        ok = write_register(XYTEKFLOW_CMD_ZERO_CAL_START[0], 1);
    }
    return ok;
}

bool XYTEKFlow::enable_temperature()
{
    bool ok = write_register(XYTEKFLOW_CMD_TEMP_PD[0], 1);
    if (ok)
    {
        delay(50);
        ok = write_register(XYTEKFLOW_CMD_TEMP_EN[0], 1);
    }
    return ok;
}

bool XYTEKFlow::read_temperature()
{
    read_registers(XYTEKFLOW_CMD_APP_REQ_TEMP[0], XYTEKFLOW_CMD_APP_REQ_TEMP[1]);
    if (received_ok)
        temperature = received_data[0];
    return received_ok;
}



void XYTEKFlow::init()
{

    //APP_UPDATE_REQ
}

void XYTEKFlow::loop(unsigned long _millis_now)
{
    millis_now = _millis_now;
    switch (read_data_stage)
    {
        case 0:
            read_flowrate();
            break;
        case 1:
            read_volume_net();
            break;
    }
    read_data_stage = (read_data_stage + 1) % 2;
}
