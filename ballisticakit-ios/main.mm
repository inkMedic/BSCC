// Released under the MIT License. See LICENSE for details.
#import <AVFAudio/AVAudioSession.h>
#import <Foundation/Foundation.h>
#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>
#import <UIKit/UIKit.h>
#include "ballistica/core/platform/platform.h"
#include "ballistica/core/support/core_config.h"
#include "ballistica/shared/ballistica.h"
namespace {
void ConfigureGameAudio() {
  // OpenAL opens a RemoteIO unit without configuring the app's session.
  // Set the category before its audio thread starts so the silent switch
  // does not mute gameplay. Allow music from other apps to keep playing.
  AVAudioSession* session = AVAudioSession.sharedInstance;
  NSError* error = nil;
  if (![session setCategory:AVAudioSessionCategoryPlayback
                       mode:AVAudioSessionModeDefault
                    options:AVAudioSessionCategoryOptionMixWithOthers
                      error:&error]) {
    NSLog(@"Cannot configure game audio session: %@", error);
    return;
  }
  if (![session setActive:YES error:&error]) {
    NSLog(@"Cannot activate game audio session: %@", error);
  }
}
}  // namespace

int main(int argc, char** argv) {
  @autoreleasepool {
    NSFileManager* fm = NSFileManager.defaultManager;
    NSString* support = [fm URLsForDirectory:NSApplicationSupportDirectory
                                   inDomains:NSUserDomainMask]
                            .firstObject.path;
    NSString* cache =
        [fm URLsForDirectory:NSCachesDirectory inDomains:NSUserDomainMask].firstObject.path;
    NSString* config = [support stringByAppendingPathComponent:@"BallisticaCommunity"];
    NSError* error = nil;
    if (![fm createDirectoryAtPath:config
            withIntermediateDirectories:YES
                             attributes:nil
                                  error:&error]) {
      NSLog(@"Cannot create configuration directory: %@", error);
      return 1;
    }
    NSBundle* bundle = NSBundle.mainBundle;
    setenv("BA_COMMUNITY", "1", 1);
    setenv("BA_COMMUNITY_IOS", "1", 1);
    setenv("BA_COMMUNITY_TABLET",
           UIDevice.currentDevice.userInterfaceIdiom == UIUserInterfaceIdiomPad ? "1" : "0", 1);
    NSString* url = [bundle objectForInfoDictionaryKey:@"CommunityAPIURL"];
    if (url.length) setenv("COMMUNITY_API_URL", url.UTF8String, 1);
    if ([[bundle objectForInfoDictionaryKey:@"CommunityAllowHTTP"] boolValue])
      setenv("COMMUNITY_ALLOW_HTTP", "1", 1);
    NSUserDefaults* defaults = NSUserDefaults.standardUserDefaults;
    NSString* uuid = [defaults stringForKey:@"CommunityInstallID"];
    if (!uuid) {
      uuid = NSUUID.UUID.UUIDString;
      [defaults setObject:uuid forKey:@"CommunityInstallID"];
    }
    setenv("BA_COMMUNITY_INSTALL_ID", uuid.UTF8String, 1);
    SDL_SetHint(SDL_HINT_ORIENTATIONS, "LandscapeLeft LandscapeRight");
    SDL_SetHint(SDL_HINT_VIDEO_ALLOW_SCREENSAVER, "0");
    auto cfg = ballistica::core::CoreConfig::ForArgsAndEnvVars(
        argc, argv, ballistica::core::Platform::TimeSinceEpochSeconds());
    cfg.config_dir = config.UTF8String;
    cfg.cache_dir = cache.UTF8String;
    cfg.user_python_dir = std::string(config.UTF8String) + "/mods";
    cfg.data_dir = std::string(bundle.resourcePath.UTF8String);
    cfg.dont_write_bytecode = true;
    ConfigureGameAudio();
    return ballistica::MonolithicMain(cfg);
  }
}
