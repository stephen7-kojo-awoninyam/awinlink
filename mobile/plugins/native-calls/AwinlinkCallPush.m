#import "AwinlinkCallPush.h"
#import <PushKit/PushKit.h>
#import <RNCallKeep/RNCallKeep.h>
#import <RNVoipPushNotification/RNVoipPushNotificationManager.h>

@interface AwinlinkCallPush () <PKPushRegistryDelegate>
@property(nonatomic, strong) PKPushRegistry *registry;
@end

@implementation AwinlinkCallPush
+ (void)start {
  static AwinlinkCallPush *instance;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    [RNCallKeep setup:@{@"appName": @"Awinlink", @"supportsVideo": @YES,
                       @"maximumCallGroups": @1, @"maximumCallsPerCallGroup": @1,
                       @"includesCallsInRecents": @NO}];
    instance = [AwinlinkCallPush new];
    instance.registry = [[PKPushRegistry alloc] initWithQueue:dispatch_get_main_queue()];
    instance.registry.delegate = instance;
    instance.registry.desiredPushTypes = [NSSet setWithObject:PKPushTypeVoIP];
  });
}
- (void)pushRegistry:(PKPushRegistry *)registry didUpdatePushCredentials:(PKPushCredentials *)credentials forType:(PKPushType)type {
  [RNVoipPushNotificationManager didUpdatePushCredentials:credentials forType:type];
}
- (void)pushRegistry:(PKPushRegistry *)registry didInvalidatePushTokenForType:(PKPushType)type {
  // The server removes invalid tokens on APNs 410 responses; a new token is registered on refresh.
}
- (void)pushRegistry:(PKPushRegistry *)registry didReceiveIncomingPushWithPayload:(PKPushPayload *)payload forType:(PKPushType)type withCompletionHandler:(void (^)(void))completion {
  NSDictionary *data = payload.dictionaryPayload;
  NSString *uuid = [data[@"uuid"] isKindOfClass:NSString.class] ? data[@"uuid"] : NSUUID.UUID.UUIDString;
  if (![[NSUUID alloc] initWithUUIDString:uuid]) uuid = NSUUID.UUID.UUIDString;
  NSString *name = [data[@"caller_name"] isKindOfClass:NSString.class] ? data[@"caller_name"] : @"Awinlink user";
  // Report directly from PushKit before waiting for JavaScript or a network round trip.
  [RNCallKeep reportNewIncomingCall:uuid handle:[data[@"call_id"] description] ?: @"Awinlink"
      handleType:@"generic" hasVideo:[data[@"call_type"] isEqual:@"VIDEO"]
      localizedCallerName:name supportsHolding:NO supportsDTMF:NO supportsGrouping:NO
      supportsUngrouping:NO fromPushKit:YES payload:data withCompletionHandler:completion];
  [RNVoipPushNotificationManager didReceiveIncomingPushWithPayload:payload forType:type];
  // A delayed push must still be reported to CallKit, then immediately ended.
  if ([data[@"expires_at"] doubleValue] <= NSDate.date.timeIntervalSince1970) {
    [RNCallKeep endCallWithUUID:uuid reason:3];
  } else {
    NSTimeInterval remaining = MIN(30, [data[@"expires_at"] doubleValue] - NSDate.date.timeIntervalSince1970);
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(remaining * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
      if (![RNCallKeep isCallActive:uuid]) [RNCallKeep endCallWithUUID:uuid reason:3];
    });
  }
}
@end
