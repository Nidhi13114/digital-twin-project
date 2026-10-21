#include <stdint.h>

#define PERIPH_BASE             (0x40000000UL)
#define APB1PERIPH_BASE         (PERIPH_BASE)
#define AHB1PERIPH_BASE         (0x40020000UL)

#define USART2_BASE             (APB1PERIPH_BASE + 0x4400UL)
#define RCC_BASE                (AHB1PERIPH_BASE + 0x3800UL)
#define GPIOA_BASE              (AHB1PERIPH_BASE + 0x0000UL)

#define AHB1ENR                 (*(volatile uint32_t *)(RCC_BASE + 0x30))
#define APB1ENR                 (*(volatile uint32_t *)(RCC_BASE + 0x40))

#define GPIOA_MODER             (*(volatile uint32_t *)(GPIOA_BASE + 0x00))
#define GPIOA_AFRL              (*(volatile uint32_t *)(GPIOA_BASE + 0x20))
#define GPIOA_OSPEEDR           (*(volatile uint32_t *)(GPIOA_BASE + 0x08))

#define USART_SR                (*(volatile uint32_t *)(USART2_BASE + 0x00))
#define USART_DR                (*(volatile uint32_t *)(USART2_BASE + 0x04))
#define USART_BRR               (*(volatile uint32_t *)(USART2_BASE + 0x08))
#define USART_CR1               (*(volatile uint32_t *)(USART2_BASE + 0x0C))
#define USART_CR2               (*(volatile uint32_t *)(USART2_BASE + 0x10))

char uart_buffer[64];

void uart_init(){
    // 1. Enable GPIOA in AHB1ENR = Set Bit 0
    AHB1ENR |= (1 << 0);
    // 2. Enable USART2 clock in APB1ENR = Set Bit 17
    APB1ENR |= (1 << 17);
    
    /* 3. Set TX(PA2) and RX(PA3) pin as AF = 10
        GPIOA_MODER[4] = 0
        GPIOA_MODER[5] = 1
        GPIOA_MODER[6] = 0
        GPIOA_MODER[7] = 1
    */
    GPIOA_MODER &= ~(1 << 4); // clear
    GPIOA_MODER |= (1 << 5);  // set
    GPIOA_MODER &= ~(1 << 6); // clear
    GPIOA_MODER |= (1 << 7);  // set
    /* 4. Set the alternate function as AF7 = 0111 for USART comm
        GPIOA_AFRL[8] = 1
        GPIOA_AFRL[9] = 1
        GPIOA_AFRL[10] = 1
        GPIOA_AFRL[11] = 0
        GPIOA_AFRL[12] = 1
        GPIOA_AFRL[13] = 1
        GPIOA_AFRL[14] = 1
        GPIOA_AFRL[15] = 0
    */
    GPIOA_AFRL |= (1 << 8);
    GPIOA_AFRL |= (1 << 9);
    GPIOA_AFRL |= (1 << 10);
    GPIOA_AFRL &= ~(1 << 11);
    GPIOA_AFRL |= (1 << 12);
    GPIOA_AFRL |= (1 << 13);
    GPIOA_AFRL |= (1 << 14);
    GPIOA_AFRL &= ~(1 << 15);
    
    /* 5. Set the speed of TX and RX(OPTIONAL) in GPIOA_OSPEEDR
       GPIOA_OSPEEDR[4] = 0
       GPIOA_OSPEEDR[5] = 1
       GPIOA_OSPEEDR[6] = 0
       GPIOA_OSPEEDR[7] = 1
    */
    GPIOA_OSPEEDR &= ~(1 << 4);
    GPIOA_OSPEEDR |= (1 << 5);
    GPIOA_OSPEEDR &= ~(1 << 6);
    GPIOA_OSPEEDR |= (1 << 7);
    
    // 6. Configure M bit for setting data word length (8 or 9 bits)
    USART_CR1 &= ~(1 << 12);
    /* 7. Configure the number of stop bits in CR2 (12 & 13)
        USART_CR2[12] = 0
        USART_CR2[13] = 0
    */
    USART_CR2 &= ~(1 << 12);
    USART_CR2 &= ~(1 << 13);
    /* 8. Set the baud rate to 9600
          Mantissa = 104
          Fraction = 3 [0011] 
    */
    USART_BRR = 0x683;
    // 9. Set USART enable in USART_CR1 (bit 13)
    USART_CR1 |= (1 << 13);
    // 10. Set the RE bit in USART_CR1 (bit 2)
    USART_CR1 |= (1 << 2);
    // 11. Set the TE bit in USART_CR1 (bit 3)
    USART_CR1 |= (1 << 3);
}

void uart_tx_char(char c){
    // 1. Check if transmit register is ready for new data
    while (!(USART_SR & (1 << 7)));
    // 2. Write the data to send in the USART_DR register
    USART_DR = c;
    // 3. Check if TC is set to see if transmission is done.
    //while (!(USART_SR & (1 << 6)));
}

#ifdef BLOCKING
char uart_rx_char(){
    // 1. Check if RXNE bit is set to see if char is recieved
    while (!(USART_SR & (1 << 5)));
    return (char) USART_DR;
} // blocking reciever
#endif

int uart_rx_char_non_blocking(char *c){
    if ((USART_SR & (1 << 5)))
    {
        *c = (char)USART_DR;
        return 1;
    }
    return 0;
}

void uart_tx_string(char arr[]){
    int i = 0;
    while (arr[i] != '\0')
    {
        uart_tx_char(arr[i]);
        i++;
    } 
}

#ifdef BLOCKING
int uart_rx_string(char arr[],int max_len){
    char c = 0;
    int i = 0;
    while (i < (max_len - 1))
    {
        c = uart_rx_char();
        if (c == '\b')
        {
            if (i > 0)
            {
                i--;
                uart_tx_string("\b \b");
            }
        return 0;
        }
        
        if (c == '\r' || c == '\n')
        {
            uart_tx_char('\r');
            uart_tx_char('\n');
            break;
        }

        arr[i] = c;
        uart_tx_char(c);
        i++;
    }
    arr[i] = '\0';
    return 1;
}
#endif

int uart_rx_string_non_blocking(char *buf, int len)
{
    static int index = 0;
    char c;

    if (!uart_rx_char_non_blocking(&c))
        return 0;

    if (c == '\b'){
        if (index > 0)
        {
            index--;
            uart_tx_string("\b \b");
        }
        return 0;
    }
    
    if (c == '\r' || c == '\n')
    {
        buf[index] = '\0';
        index = 0;
        uart_tx_string("\r\n");
        return 1;
    }

    if (index < len - 1)
    {
        buf[index++] = c;
        uart_tx_char(c);
    }

    return 0;
}

int main(void)
{
    uart_init();

    uart_tx_string("BOOT_OK\r\n");

    while (1)
    {
        /* Keep the firmware running after boot */
    }
}
