import type {LuxonisReport} from '../../src/station/luxonisContract';
const jpeg='/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAIBAQEBAQIBAQECAgICAgQDAgICAgUEBAMEBgUGBgYFBgYGBwkIBgcJBwYGCAsICQoKCgoKBggLDAsKDAkKCgr/2wBDAQICAgICAgUDAwUKBwYHCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgr/wAARCAAYACADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDi6KKK/ic/vQ9Mooor+uD/AJqzzOiiiv5HP+lQ9Mooor+uD/mrP//Z';
export function luxonisFixture(active=false,preview=false,now=Date.now()/1000):LuxonisReport {
  const frame={stamp:now-.25,sourceWidth:1920,sourceHeight:1080,width:32,height:24,jpeg,encoding:'bgr8'};
  return {schema:'vision.api.luxonis.v1',source:'STATION',instanceId:'f'.repeat(32),capturedAt:now,model:'OAK-D Pro AF',
    hardwareConnection:'USB_DETECTED',observer:'ACTIVE',graph:active?'ACTIVE':'NO_NODE',
    node:active?{domain:186,name:'/oak'}:null,
    endpoints:{rgb:active?'AVAILABLE':'UNAVAILABLE',depth:active?'AVAILABLE':'UNAVAILABLE'},
    settings:active?{'rgb.i_fps':15,'driver.i_enable_ir':false,'rgb.r_set_man_focus':false}: {},
    settingsAt:active?now-.1:null,
    profiles:{rgbd_lab:{'rgb.i_fps':15,'driver.i_enable_ir':false},stereo800_lab:{'stereo.i_width':1280,'stereo.i_height':800,'stereo.i_subpixel':true}},
    frames:{rgb:active&&preview?frame:null,depth:active&&preview?{...frame,encoding:'16UC1'}:null},previewAllowed:true};
}
