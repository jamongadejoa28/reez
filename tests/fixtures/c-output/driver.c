#include <stdio.h>
void dispatch_event(int,int);
int state_checksum(void);
int main(void) {
    printf("%d\n", state_checksum());
    dispatch_event(0,3); printf("%d\n", state_checksum());
    dispatch_event(1,2); printf("%d\n", state_checksum());
    dispatch_event(2,0); printf("%d\n", state_checksum());
    dispatch_event(0,-9); printf("%d\n", state_checksum());
    return 0;
}
