// Sky-Walkers 2021-2023
// Library for controlling XY-TEK flow sensor.

// https://github.com/4-20ma/ModbusMaster
// https://github.com/4-20ma/ModbusMaster/blob/master/examples/RS485_HalfDuplex/RS485_HalfDuplex.ino
// Operate in master (client) mode: Arduino makes a query, sensor responds

#ifndef XYTEKFlow_h
#define XYTEKFlow_h

#include "Arduino.h"
#include "ModbusMaster2.h"	// MODBUS for Flow sensor

//#define XYTEKFLOW_SERIAL_TIMEOUT_MS	200	// Hardcoded in lib code, private ku16MBResponseTimeout, line 252, https://github.com/4-20ma/ModbusMaster/blob/master/src/ModbusMaster.h
                                            // To change it go to source file. Use code provided here. Copy to:
                                            // C:\Users\Sky-Walkers\Documents\Arduino\libraries\ModbusMaster2\src
                                            // /home/sky/.arduino15/libraries

// Protocol commands
// byte (uint32 or float) format order:
//		[lower_MSB, lower_LSB, higher_MSB, higher_LSB]
//		[	1,			0,			3,			2	 ]
// ---
// Communication protocol               command:            addr,   n_r,    // n_r is number of 16-bit registers requested
static const uint16_t XYTEKFLOW_CMD_APP_UPDATE_REQ[]    = {0x200,	1};     // Update parameter commands
// static const uint16_t XYTEKFLOW_CMD_SAMPLE_PER_SECOND[]  = {0x244,   1}; // The output points of flow rate data per second, range: 1，2，5，10，20，50
static const uint16_t XYTEKFLOW_CMD_ZERO_CAL_TIME[]     = {0x2A6,	2};     // Zero calibration time, unit: second
static const uint16_t XYTEKFLOW_CMD_TEMP_PD[]           = {0x2A2,   1};     // Temperature sampling period. 0: no sampling; non-zero: sampling period, in seconds.
static const uint16_t XYTEKFLOW_CMD_TEMP_EN[]           = {0x2A8,   1};     // Disable/enable read temperature. 0: system does not read temperature, 1: system reads temperature value according to the period (s) defined by TEMP_PD.
static const uint16_t XYTEKFLOW_CMD_RESET_VOLUME[]      = {0x400,	1};     // Clear the accumulated flow of the sensor. Send this command and write "1" to set the accumulated flow to 0.
static const uint16_t XYTEKFLOW_CMD_ZERO_CAL_START[]    = {0x401,	1};     // Write "1" to start zero offset calibration. Afterwards, you can determine whether the zero offset calibration is completed by reading the "ZERO_CAL_TAG" parameter
static const uint16_t XYTEKFLOW_CMD_SEARCH_DEVICE[]     = {0x613,	2};     // Used for the host to automatically search for devices on the bus. A device reply character "XYKJ" at an address indicates that the device is on the bus
static const uint16_t XYTEKFLOW_CMD_APP_REQ_VOL[]       = {0x809,	2};     // Accumulated flow
static const uint16_t XYTEKFLOW_CMD_SYSTEM_STAT[]       = {0x813,	1};     // System status，lower 8 bit means:
                                                                            //  12: in zero calibration status
                                                                            // 121: parameters check error
                                                                            // 122: normal running status
                                                                            // 126: no ultrasonic receive signal (no liquid or bubble in the tubing)
static const uint16_t XYTEKFLOW_CMD_APP_REQ_TEMP[]      = {0x815,   1};     // Read 16bit temperature value. The value divided by 10 is the real temperature
static const uint16_t XYTEKFLOW_CMD_ZERO_CAL_TAG[]      = {0x9AD,   1};     // Zero offset calibration completed flag. 0: Zero offset calibration is not completed; 1: Zero offset calibration is completed, you can start to read the zero offset value （zero_cal_value）
static const uint16_t XYTEKFLOW_CMD_ZERO_CAL_VALUE[]    = {0x9AE,   2};     // Zero offset value
static const uint16_t XYTEKFLOW_CMD_USER_INFO[]         = {0x9B0,   8};     // 16 user-defined characters, allowed to be written in user tools and stored in the sensor.
static const uint16_t XYTEKFLOW_CMD_USR_REQ_BUB_STAT[]  = {0x1000,  2};	    // Air bubble status in the last 32 work cycle, 1 indicates there are air bubbles in the flow channel, and 0 indicates there is liquid in the flow channel. The lowest bit represents the current state, and the highest bit represents the air
static const uint16_t XYTEKFLOW_CMD_USR_REQ_VOL[]       = {0x1002,	2};     // Net total volume
static const uint16_t XYTEKFLOW_CMD_USR_REQ_POS_VOL[]   = {0x1004,	2};     // Total volume in positive direction
static const uint16_t XYTEKFLOW_CMD_USR_REQ_NEG_VOL[]   = {0x1006,	2};     // Total volume in negative direction
static const uint16_t XYTEKFLOW_CMD_USR_REQ_FLOW_RATE_REALTIME[]    = {0x1008,  2};    // Instantaneous flow rate, update real-time according to system work cycle
static const uint16_t XYTEKFLOW_CMD_USR_REQ_FLOW_RATE_AVG1S[]       = {0x100A,  2};    // Averaged flow rate (moving average in 1 second), update rate 10Hz
static const uint16_t XYTEKFLOW_CMD_USR_REQ_FLOW_RATE_AVG2S[]       = {0x100C,  2};    // Averaged flow rate (moving average in 2 seconds), update rate 1Hz


class XYTEKFlow
{
    public:
        XYTEKFlow(HardwareSerial* serial_, uint8_t id_, void (*pre_transmission)(), void (*post_transmission)());
        void init();
        void loop(unsigned long _millis_now);
        
        bool read_flowrate();
        bool read_volume_net();
        bool read_volume_pos();
        bool read_volume_neg();
        bool search_device();
        bool read_status();
        bool reset_volume();
        bool zero_calibration();
        bool enable_temperature();
        bool read_temperature();

        float flow_rate;
        float flow_volume_net;
        float flow_volume_pos;
        float flow_volume_neg;
        uint16_t temperature;
        uint32_t search_device_response;
        uint16_t system_status;

    private:
        HardwareSerial* serial;		// Serial port
        uint8_t id;					// Device ID
        ModbusMaster2 node;			// ModbusMaster2 object

        bool write_register(uint16_t data_address, uint16_t value);
        bool write_registers(uint16_t data_address, uint16_t* data, uint16_t length);
        bool read_registers(uint16_t data_address, uint16_t request_words);
        float received_data_to_float(uint8_t offset);
        bool received_ok;
        uint8_t received_length;
        uint16_t received_data[40];
        unsigned long millis_now;
        uint8_t read_data_stage;

        union float_temp {
            float f;
            uint8_t  u8[4];
            uint16_t u16[2];
        } ftemp;

        union word_temp {
            uint32_t u32;
            uint8_t  u8[4];
            uint16_t u16[2];
        } wtemp;

};

#endif
