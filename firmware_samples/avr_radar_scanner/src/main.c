#define F_CPU 8000000UL
#include <avr/io.h>
#include <util/delay.h>
#include <avr/interrupt.h>
#include <stdio.h>

// ==========================
// Pin definitions
// ==========================
#define SERVO_PIN PB1
#define TRIG_PIN  PB2
#define ECHO_PIN  PB3
#define LED_PIN   PB5

// LCD pins (4-bit mode, split across ports)
#define LCD_RS PD4
#define LCD_EN PD5
#define LCD_D4 PD6
#define LCD_D5 PD7
#define LCD_D6 PB0
#define LCD_D7 PC0

// ==========================
// Globals
// ==========================
volatile uint32_t echo_ticks = 0;  
volatile uint8_t  measuring  = 0;  
uint16_t distance = 0;
uint8_t  angle    = 0;
int8_t   direction = 1;

// ==========================
// UART
// ==========================
void uart_init(unsigned int ubrr) {
    UBRR0H = (unsigned char)(ubrr >> 8);
    UBRR0L = (unsigned char)ubrr;         
    UCSR0B = (1 << TXEN0);
    UCSR0C = (1 << UCSZ01) | (1 << UCSZ00); // 8N1
}

void uart_transmit(unsigned char data) {
    while (!(UCSR0A & (1 << UDRE0)));
    UDR0 = data;
}

void uart_print(const char *str) {
    while (*str) uart_transmit(*str++);
}

void uart_print_num(uint16_t num) {
    char buf[8];
    sprintf(buf, "%u", num);
    uart_print(buf);
}

// ==========================
// LCD 
// ==========================
void lcd_pulse_enable(void) {
    PORTD |=  (1 << LCD_EN);
    _delay_us(1);
    PORTD &= ~(1 << LCD_EN);
    _delay_us(100);
}

void lcd_send_nibble(uint8_t nibble) {
    if (nibble & 0x01) PORTD |=  (1 << LCD_D4); else PORTD &= ~(1 << LCD_D4);
    if (nibble & 0x02) PORTD |=  (1 << LCD_D5); else PORTD &= ~(1 << LCD_D5);
    if (nibble & 0x04) PORTB |=  (1 << LCD_D6); else PORTB &= ~(1 << LCD_D6);
    if (nibble & 0x08) PORTC |=  (1 << LCD_D7); else PORTC &= ~(1 << LCD_D7);
    lcd_pulse_enable();
}

void lcd_send(uint8_t value, uint8_t rs) {
    if (rs) PORTD |= (1 << LCD_RS); else PORTD &= ~(1 << LCD_RS);
    lcd_send_nibble(value >> 4);
    lcd_send_nibble(value & 0x0F);
}

void lcd_command(uint8_t cmd) {
    lcd_send(cmd, 0);
    _delay_ms(2);
}

void lcd_data(uint8_t data) {
    lcd_send(data, 1);
    _delay_us(50);
}

void lcd_init(void) {
    DDRD |= (1 << LCD_RS) | (1 << LCD_EN) | (1 << LCD_D4) | (1 << LCD_D5);
    DDRB |= (1 << LCD_D6);
    DDRC |= (1 << LCD_D7);

    _delay_ms(40);
    lcd_send_nibble(0x03); _delay_ms(5);
    lcd_send_nibble(0x03); _delay_us(100);
    lcd_send_nibble(0x03);
    lcd_send_nibble(0x02);      // switch to 4-bit mode

    lcd_command(0x28);           // 2 lines, 5×8 font
    lcd_command(0x0C);           // display on, cursor off
    lcd_command(0x06);           // auto-increment, no shift
    lcd_command(0x01);           // clear (only called once during init)
    _delay_ms(2);
}

void lcd_goto(uint8_t row, uint8_t col) {
    uint8_t addr = (row ? 0x40 : 0x00) + col;
    lcd_command(0x80 | addr);
}

void lcd_print(const char *str) {
    while (*str) lcd_data(*str++);
}

void lcd_print_num(uint16_t num) {
    char buf[6];
    sprintf(buf, "%u", num);
    lcd_print(buf);
}

// ==========================
// Servo — Timer1
// ==========================
void servo_init(void) {
    DDRB |= (1 << SERVO_PIN);
    TCCR1A = (1 << COM1A1) | (1 << WGM11);
    TCCR1B = (1 << WGM13) | (1 << WGM12) | (1 << CS11);  // prescaler 8
    ICR1 = 19999;                                           // 20 ms period
}

void servo_set_angle(uint8_t a) {
    // 0° → 1 ms pulse (OCR1A = 1000)
    // 180° → 2 ms pulse (OCR1A = 2000)
    OCR1A = 1000 + (a * 1000UL) / 180;
}

// ==========================
// Ultrasonic
// ==========================

// FIX 1: was called in main() but undefined — linker error.
void ultrasonic_init(void) {
    DDRB |=  (1 << TRIG_PIN);   // TRIG = output
    DDRB &= ~(1 << ECHO_PIN);   // ECHO = input  
    TCCR2A = 0;                  
    TCCR2B = (1 << CS21);       
    TIMSK2 |= (1 << TOIE2);     
}

void ultrasonic_trigger(void) {
    PORTB &= ~(1 << TRIG_PIN);
    _delay_us(2);
    PORTB |=  (1 << TRIG_PIN);
    _delay_us(10);
    PORTB &= ~(1 << TRIG_PIN);
}

uint16_t ultrasonic_get_distance(void) {
    ultrasonic_trigger();

    // Wait for echo rising edge
    uint32_t timeout = 0;
    while (!(PINB & (1 << ECHO_PIN))) {
        if (++timeout > 60000) return 0;
    }

    measuring  = 1;
    echo_ticks = 0;
    TCNT2      = 0;

    timeout = 0;
    while (PINB & (1 << ECHO_PIN)) {
        if (++timeout > 60000) { measuring = 0; return 0; }
    }

    cli();
    measuring = 0;
    uint8_t  tcnt2_snap = TCNT2;
    uint32_t ticks_snap = echo_ticks;
    sei();

    uint32_t echo_time = ticks_snap + tcnt2_snap;
    return (uint16_t)((echo_time * 17) / 1000);
}

ISR(TIMER2_OVF_vect) {
    if (measuring) echo_ticks += 256UL;
}

// ==========================
// LED
// ==========================
void led_init(void)   { DDRB |=  (1 << LED_PIN); }
void led_toggle(void) { PORTB ^= (1 << LED_PIN); }

// ==========================
// MAIN
// ==========================
int main(void) {
    uart_init(51);       // 9600 baud @ 8 MHz
    servo_init();
    ultrasonic_init();   // FIX 1: now defined
    led_init();
    lcd_init();
    sei();

    servo_set_angle(90);
    _delay_ms(1000);

    while (1) {
        servo_set_angle(angle);
        _delay_ms(300);

        distance = ultrasonic_get_distance();

        // UART: "angle,distance\r\n" — parsed by the Python GUI
        uart_print_num(angle);
        uart_print(",");
        uart_print_num(distance);
        uart_print("\r\n");

        lcd_goto(0, 0);
        lcd_print("Ang:");
        lcd_print_num(angle);
        lcd_print("   ");   // erase leftover digits from wider previous value

        lcd_goto(1, 0);
        lcd_print("Dst:");
        lcd_print_num(distance);
        lcd_print("cm  "); // erase leftover digits

        led_toggle();

        // Sweep 0° – 180° – 0° in 5° steps
        angle += direction * 5;
        if      (angle >= 180) { angle = 180; direction = -1; }
        else if (angle <= 0)   { angle = 0;   direction =  1; }
    }
}
